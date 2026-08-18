"""DQ-enriched orchestrator for /cc and /auto Telegram commands.

Uses domain_classifier centroids for project detection,
reads PROJECT.md for context, and runs Claude Code as async subprocess
with progressive Telegram feedback.

Usage from bot:
    from orchestrator import detect_project, build_context, parse_output
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import unicodedata
from pathlib import Path

log = logging.getLogger(__name__)

DQIII8_ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
PROJECTS_DIR = DQIII8_ROOT / "my-projects"
LESSONS_PATH = DQIII8_ROOT / "tasks" / "lessons.md"

# ── Project detection via keyword centroids ───────────────────────────────────

# Each project has keyword centroids (same principle as domain_classifier).
# Scanned dynamically at import from PROJECT.md files.

_PROJECT_KEYWORDS: dict[str, list[str]] = {}


def _scan_projects() -> None:
    """Build keyword index from my-projects/*/PROJECT.md files.

    Extracts keywords from:
    1. `Keywords:` field in PROJECT.md (highest signal, curated)
    2. Project directory name parts
    3. `Entry:` field
    """
    if _PROJECT_KEYWORDS:
        return
    if not PROJECTS_DIR.is_dir():
        return
    for d in sorted(PROJECTS_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith((".", "_")):
            continue
        pm = d / "PROJECT.md"
        if not pm.exists():
            continue
        text = pm.read_text(encoding="utf-8")
        text_lower = text.lower()

        words: set[str] = set()

        # 1. Curated keywords (most reliable) — normalize accents
        kw_match = re.search(r"keywords?:\s*(.+)", text_lower)
        if kw_match:
            words.update(
                _normalize(w.strip())
                for w in kw_match.group(1).split(",")
                if len(w.strip()) >= 3
            )

        # 2. Project name parts
        words.update(p for p in d.name.split("-") if len(p) >= 3)

        # 3. Entry field
        entry_match = re.search(r"entry:\s*(.+)", text_lower)
        if entry_match:
            words.update(re.findall(r"[a-záéíóúñü]{4,}", entry_match.group(1)))

        _PROJECT_KEYWORDS[d.name] = sorted(words)


def _normalize(text: str) -> str:
    """Strip accents for matching: diagnóstico → diagnostico."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def detect_project(prompt: str) -> dict:
    """Detect which project a prompt refers to using keyword centroids.

    Returns dict with keys: name, path, project_md (content or None).
    Falls back to DQIII8 root if no match.
    """
    _scan_projects()
    prompt_lower = _normalize(prompt.lower())
    prompt_words = set(re.findall(r"[a-z]{3,}", prompt_lower))

    best_name: str | None = None
    best_hits = 0

    for project_name, keywords in _PROJECT_KEYWORDS.items():
        norm_keywords = {_normalize(k) for k in keywords}
        hits = len(prompt_words & norm_keywords)
        # Also check substring matches for project name
        if project_name.replace("-", " ") in prompt_lower:
            hits += 5
        if project_name.replace("-", "") in prompt_lower:
            hits += 5
        if hits > best_hits:
            best_hits = hits
            best_name = project_name

    if best_name and best_hits >= 2:
        project_path = PROJECTS_DIR / best_name
        pm = project_path / "PROJECT.md"
        content = pm.read_text(encoding="utf-8") if pm.exists() else None
        log.info("Detected project: %s (%d keyword hits)", best_name, best_hits)
        return {"name": best_name, "path": project_path, "project_md": content}

    return {"name": "dqiii8", "path": DQIII8_ROOT, "project_md": None}


def build_context(project: dict, prompt: str) -> str | None:
    """Build enriched system prompt from project context + lessons.

    Returns system prompt string, or None if no enrichment needed.
    """
    parts: list[str] = []

    if project["project_md"]:
        parts.append(f"PROJECT CONTEXT ({project['name']}):")
        parts.append(project["project_md"][:2000])

    # Last 20 lines of lessons.md
    if LESSONS_PATH.exists():
        lines = LESSONS_PATH.read_text(encoding="utf-8").strip().split("\n")
        recent = lines[-20:] if len(lines) > 20 else lines
        if recent:
            parts.append("\nRECENT LESSONS:")
            parts.append("\n".join(recent))

    if not parts:
        return None

    return "\n".join(parts)


def prepare_project(project: dict) -> dict:
    """Detect project + ensure Tier 3 plugins + build context.

    Returns project dict with 'auto_installed_plugins' key added.
    """
    from plugin_manager import ensure_plugins, get_project_plugins

    plugins_needed = get_project_plugins(project)
    if plugins_needed:
        installed = ensure_plugins(project)
        project["auto_installed_plugins"] = installed
    else:
        project["auto_installed_plugins"] = []
    return project


def parse_output(raw: str, cwd: Path) -> dict:
    """Parse Claude Code output to extract files, summary, and next steps.

    Returns: {files: list[Path], summary: str, errors: list[str], next_steps: list[str]}
    """
    files: list[Path] = []
    seen: set[str] = set()
    errors: list[str] = []
    next_steps: list[str] = []

    # Detect file paths
    for pattern in [
        r"(?:Created|Wrote|Saved|Generated|Output)[:\s]+(.+\.(?:docx|pdf|png|xlsx|json|py|md))",
        r"(data/outputs/[^\s]+\.(?:docx|pdf|png))",
        r"(/[\w/\-_.]+\.(?:docx|pdf|png|xlsx))",
    ]:
        for m in re.finditer(pattern, raw, re.IGNORECASE):
            path_str = m.group(1).strip().rstrip(".,;)")
            p = Path(path_str) if Path(path_str).is_absolute() else cwd / path_str
            if p.exists() and str(p) not in seen:
                files.append(p)
                seen.add(str(p))

    # Detect errors
    for line in raw.split("\n"):
        if re.search(r"error|failed|exception|traceback", line, re.IGNORECASE):
            errors.append(line.strip()[:200])

    # Extract next steps (common patterns in Claude output)
    in_next = False
    for line in raw.split("\n"):
        if re.search(r"next\s*steps?|todo|pending|remaining", line, re.IGNORECASE):
            in_next = True
            continue
        if in_next and line.strip().startswith(("-", "*", "•", "1", "2", "3")):
            next_steps.append(line.strip()[:150])
        elif in_next and not line.strip():
            in_next = False

    # Summary: last 10 non-empty lines
    lines = [l.strip() for l in raw.split("\n") if l.strip()]
    summary = "\n".join(lines[-10:]) if lines else "(no output)"

    return {
        "files": files,
        "summary": summary[:3000],
        "errors": errors[:5],
        "next_steps": next_steps[:5],
    }


# ── Phase detection for progress updates ──────────────────────────────────────


def detect_phase(lines: list[str]) -> str:
    """Detect current execution phase from recent output lines."""
    recent = "\n".join(lines[-20:]).lower()

    phases = [
        ("quality", "Quality review"),
        ("phase 5", "Quality review"),
        ("docx", "DOCX assembly"),
        ("phase 4", "DOCX assembly"),
        ("phase 3", "Plan generation"),
        ("plan", "Plan generation"),
        ("phase 2", "Diagnostic"),
        ("diagnostic", "Diagnostic"),
        ("phase 1", "Research"),
        ("research", "Research"),
        ("crawl", "Research"),
        ("commit", "Git"),
        ("push", "Git"),
        ("pytest", "Tests"),
        ("test", "Tests"),
    ]
    for keyword, label in phases:
        if keyword in recent:
            return label

    return "Working..."


def format_progress(project_name: str, phase: str, elapsed: float) -> str:
    """Format progress message for Telegram edit."""
    m, s = divmod(int(elapsed), 60)
    t = f"{m}m {s}s" if m else f"{s}s"
    return f"[{project_name}] {phase} ({t})"


# ── Tier classification for /cc ───────────────────────────────────────────────
#
# Philosophy: cheapest tier first. Local models EXECUTE, cloud models SUPERVISE.
#
#   C (Ollama qwen2.5-coder:7b) — code execution workhorse ($0, local)
#   B (Groq llama-3.3-70b)      — simple queries + code review ($0, cloud)
#   A (Sonnet)                   — planning, complex supervision, default
#   S (Opus)                     — only when A produces poor results (escalation)
#
# Opus is NEVER a first-choice. It's an escalation from Sonnet.

# Execution verbs — require filesystem/bash access → Sonnet (claude -p)
_EXEC_VERBS = frozenset(
    {
        "implementa",
        "implement",
        "crea",
        "create",
        "fix",
        "arregla",
        "refactor",
        "añade",
        "add",
        "modifica",
        "modify",
        "actualiza",
        "update",
        "deploy",
        "instala",
        "install",
        "ejecuta",
        "run",
        "genera",
        "generate",
        "escribe",
        "write",
        "borra",
        "delete",
        "mueve",
        "move",
        "renombra",
        "rename",
        "commit",
        "push",
        "lista",
        "list",
        "test",
        "prueba",
    }
)

# Code keywords that imply execution context (not just discussion)
_EXEC_KW = frozenset(
    {
        "traceback",
        "refactor",
        "debug",
        "dockerfile",
        "git ",
        "npm",
        "pip",
    }
)

# Planning keywords — need Sonnet-level reasoning (not code generation)
_PLANNING_KW = frozenset(
    {
        "plan",
        "planifica",
        "diseña",
        "design",
        "analiza",
        "analyze",
        "compara",
        "compare",
        "evalúa",
        "evaluate",
        "revisa",
        "review",
        "audita",
        "audit",
        "investiga",
        "research",
        "architecture",
        "arquitectura",
        "strategy",
        "estrategia",
    }
)


def _has_exec_keywords(lower: str) -> bool:
    """Check if prompt contains keywords that imply execution context."""
    for kw in _EXEC_KW:
        if len(kw) <= 4:
            if re.search(r"\b" + re.escape(kw) + r"\b", lower):
                return True
        else:
            if kw in lower:
                return True
    return False


def detect_task_type(prompt: str) -> str:
    """Return the broad task category for a /cc prompt.

    Returns one of: "planning", "execution", "knowledge".
    Pure function — no side effects, independently testable.
    """
    lower = prompt.lower()
    words = set(lower.split())

    if words & _PLANNING_KW:
        return "planning"
    if words & _EXEC_VERBS or _has_exec_keywords(lower):
        return "execution"
    return "knowledge"


def select_tier(task_type: str, prompt_len: int = 0) -> str:
    """Map a task type to an execution tier letter.

    C = Qwen local ($0, text-only context injection, no tools)
    A = Sonnet via claude -p (filesystem/bash access)

    Returns "C" or "A". Never returns "S" directly — escalation is
    handled separately by should_fallback().
    """
    if task_type in ("planning", "execution"):
        return "A"
    if prompt_len > 300:
        return "A"
    return "C"


def classify_cc_tier(prompt: str) -> str:
    """Classify a /cc prompt into execution tier.

    Thin wrapper around detect_task_type() + select_tier().
    Returns "C" or "A". Never returns "S" directly.
    """
    return select_tier(detect_task_type(prompt), len(prompt))


# ── 5-level task complexity classifier ───────────────────────────────────────
#
# Maps a prompt to one of five COMPLEXITY CLASSES used by the Claude Code
# routing rules (ml-routing.md / token-routing.md).
#
# Naming (audit gap 9, 2026-08-17): these are complexity classes, NOT "tiers".
# "Tier" is reserved for the single canonical cost taxonomy C/B/B+/B++/A/S
# (see .claude/rules/03_tiering_and_routing.md). Complexity class → executor is
# a different axis; do not conflate the two vocabularies.
#
#   READ_ONLY    — no writes, pure observation (grep, ls, cat, git log)
#   SIMPLE_WRITE — single file or trivial multi-step (run tests, git commit)
#   CODE_GEN     — generate new functions/files, simple refactor
#   ARCHITECTURE — multi-file refactor, system design, planning
#   CRITICAL     — production/security/deploy — plan-gate always active

_RO_VERBS = frozenset(
    {
        "grep",
        "find",
        "ls",
        "list",
        "cat",
        "head",
        "tail",
        "show",
        "read",
        "lee",
        "muestra",
        "busca",
        "search",
        "describe",
        "explain",
        "explica",
        "que es",
        "how does",
        "como funciona",
        "git log",
        "git status",
        "git diff",
        "git show",
        "git branch",
        "count",
        "cuantos",
        "how many",
    }
)

_SIMPLE_WRITE_VERBS = frozenset(
    {
        "pytest",
        "test",
        "prueba",
        "run tests",
        "git add",
        "git commit",
        "git push",
        "commit",
        "push",
        "edit",
        "edita",
        "cambia una linea",
        "fix typo",
        "arregla typo",
        "rename",
        "renombra",
        "chmod",
        "touch",
    }
)

_CODE_GEN_VERBS = frozenset(
    {
        "crea",
        "create",
        "escribe",
        "write",
        "genera",
        "generate",
        "implementa",
        "implement",
        "añade",
        "add",
        "función",
        "function",
        "clase",
        "class",
        "refactor",
        "simplifica",
        "simplify",
        "extract",
        "extrae",
    }
)

_ARCH_KW = frozenset(
    {
        "diseña",
        "design",
        "architect",
        "architecture",
        "arquitectura",
        "plan",
        "planifica",
        "multi-file",
        "multiples archivos",
        "sistema",
        "system",
        "strategy",
        "estrategia",
        "migrate",
        "migra",
        "rewrite",
        "reescribe",
        "reestructura",
        "restructure",
    }
)

_CRITICAL_KW = frozenset(
    {
        "produccion",
        "production",
        "prod",
        "deploy",
        "seguridad",
        "security",
        "secret",
        "credentials",
        "credenciales",
        "cve",
        "vulnerability",
        "vulnerabilidad",
        "exploit",
        "breach",
        "hack",
    }
)


def _kw_in(kw: str, text: str) -> bool:
    """Return True if keyword appears as whole word(s) in text."""
    return bool(re.search(r"\b" + re.escape(kw) + r"\b", text))


def classify_task_complexity(prompt: str) -> str:
    """Classify a prompt into one of five complexity classes.

    Returns one of: READ_ONLY, SIMPLE_WRITE, CODE_GEN, ARCHITECTURE, CRITICAL.

    Routing (interactive Claude Code sessions only):
        READ_ONLY    → executor-lite / explorer-lite (CC native Haiku agents, Agent tool)
        SIMPLE_WRITE → executor-lite (CC native Haiku agent, Agent tool)
        CODE_GEN     → PAL/Ollama qwen2.5-coder (if available) else Sonnet
        ARCHITECTURE → Sonnet (session principal)
        CRITICAL     → Sonnet + plan-gate (Opus review)

    NOTE: executor-lite and explorer-lite are Claude Code native agents (.claude/agents/).
    They are NOT available in autonomous_loop.sh (claude -p non-interactive mode).
    In autonomous mode all routing goes through AGENT_ROUTING in openrouter_wrapper.py.
    """
    lower = prompt.lower()
    words = set(lower.split())

    # CRITICAL — check first (highest risk, must not be downgraded)
    for kw in _CRITICAL_KW:
        if _kw_in(kw, lower):
            return "CRITICAL"

    # ARCHITECTURE — multi-file, system design
    if words & _ARCH_KW or len(prompt) > 500:
        return "ARCHITECTURE"
    for kw in _ARCH_KW:
        if _kw_in(kw, lower):
            return "ARCHITECTURE"

    # READ_ONLY — pure observation (check before CODE_GEN to avoid false positives)
    for kw in _RO_VERBS:
        if _kw_in(kw, lower):
            return "READ_ONLY"

    # SIMPLE_WRITE — single file edits, tests, git commits
    for kw in _SIMPLE_WRITE_VERBS:
        if _kw_in(kw, lower):
            return "SIMPLE_WRITE"

    # CODE_GEN — create / write / implement new code
    for kw in _CODE_GEN_VERBS:
        if _kw_in(kw, lower):
            return "CODE_GEN"

    # Default: if short and no exec verbs → READ_ONLY (safe default for Haiku)
    if len(prompt) <= 150 and not (words & _EXEC_VERBS):
        return "READ_ONLY"

    return "CODE_GEN"


_FAILURE_SIGNALS = (
    "i can't",
    "i cannot",
    "no puedo",
    "beyond my",
    "fuera de mi",
    "not possible",
    "no es posible",
)


def should_fallback(
    tier: str,
    *,
    success: bool = True,
    output: str = "",
    prompt_len: int = 0,
) -> bool:
    """Return True if the current tier should escalate to the next tier up.

    Pure function — independently testable, no side effects.

    For tier "A" (Sonnet): escalates to Opus when output is too short
    or contains explicit failure signals.
    For any tier: escalates immediately on success=False.
    """
    if not success:
        return True

    if tier == "A":
        output_lower = output.lower()
        if len(output.strip()) < 200 and prompt_len > 100:
            return True
        if any(sig in output_lower for sig in _FAILURE_SIGNALS):
            return True

    return False


def should_escalate_to_opus(prompt: str, sonnet_output: str, success: bool) -> bool:
    """Backwards-compatible wrapper around should_fallback().

    dqiii8_bot.py imports this name — preserved to avoid changing callers.
    """
    return should_fallback("A", success=success, output=sonnet_output, prompt_len=len(prompt))
