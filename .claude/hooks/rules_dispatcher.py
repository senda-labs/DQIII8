"""
DQIII8 — Rules Dispatcher (RAG de Reglas Dinámico)
Inyecta SÓLO las reglas relevantes al contexto del tool en curso.

En lugar de cargar los 16 archivos en cada turno, este módulo mapea
tool + input → subconjunto mínimo de reglas (~1144–6853 tokens, cl100k_base real).

RANGO CANÓNICO (medido con token_estimate() — real cl100k_base vía tiktoken,
ya no el heurístico de word-split que subestimaba ~30-45% — sobre la matriz de
casos representativos, incluyendo triggers combinados, de
tests/test_rules_dispatcher.py, re-medido 2026-08-18 tras el fold RC9 de
§ REGLA NIM en 00_core_behavior.md): **suelo 1144** (solo _ALWAYS =
ops + core-behavior), **techo 6853** (Bash combinando las keywords
git + agent/orchestrat + sqlite3 en un mismo comando).

RE-MEDIR OBLIGATORIAMENTE (este rango ya se ha quedado obsoleto varias veces)
siempre que cambie de tamaño 00_core_behavior.md, dqiii8-ops.md, o
cualquier fichero de rules_db/ que esté en _ALWAYS o en un trigger muy usado, y
siempre que se añada/quite un trigger. Los 4 sitios que citan el rango deben
actualizarse juntos: este docstring, DYNAMIC.md, y 02_hooks_and_permissions.md (×2).

Las reglas residen en .claude/rules_db/ (fuera del auto-inject de Claude Code).
El único archivo en .claude/rules_db/ que se auto-inyecta vía Claude Code es
.claude/rules/DYNAMIC.md; el resto de .claude/rules/*.md y .claude/rules_db/*.md
se inyectan solo bajo demanda por este dispatcher (RC4, corregido 2026-08-18 —
la afirmación anterior de "3 líneas" era obsoleta desde que DYNAMIC.md creció).
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Sequence

RULES_DB = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8")) / ".claude" / "rules_db"
# Rules split: deterministic modules live in .claude/rules/ (../rules/ from RULES_DB)
# Legacy contextual rules remain in .claude/rules_db/

# ── Rule file registry ────────────────────────────────────────────────────────
# Paths are relative to RULES_DB. Use "../rules/" for the new deterministic modules.
_REGISTRY: dict[str, str] = {
    # ── Deterministic modules (new rule engine split) ─────────────────────────
    "core-behavior":  "../rules/00_core_behavior.md",
    "db-mutations":   "../rules/01_database_mutations.md",
    "hooks-perms":    "../rules/02_hooks_and_permissions.md",
    "tiering":        "../rules/03_tiering_and_routing.md",
    # ── Legacy contextual rules (rules_db/) ───────────────────────────────────
    "git-safety":     "git-safety.md",
    "python":         "python.md",
    "ops":            "dqiii8-ops.md",
    "prevention":     "dqiii8-error-prevention.md",
    "tools":          "dqiii8-tools.md",
    "plan-gate":      "dqiii8-plan-gate.md",
    # "deliverables" / "context-window" aliases removed 2026-07-05: their files
    # never existed and no tool/keyword mapping referenced them (audit P3-15).
    # "routing" alias + routing.md removed 2026-08-17 (audit gap 12a): orphaned —
    # no tool/keyword mapping referenced it and 03_tiering_and_routing.md already
    # carries the routing table, decision algorithm and delegation rules.
    "workspace":      "workspace.md",
    "intl-reports":   "intl-reports-ops.md",
    "web-tools":      "web-research-tools.md",
    "agents":         "common/agents.md",
    "quality":        "common/quality.md",
    # "git-workflow" / "workflow" / "testing" aliases + their common/*.md files
    # removed 2026-08-17 (audit gap 12a, residual sweep): all three were orphans —
    # registered but unreachable from _ALWAYS/_TOOL_RULES/_BASH_KEYWORD_RULES/_EXT_RULES
    # — AND generic Claude Code boilerplate already superseded by wired DQIII8 files:
    #   testing.md      → python.md § Testing (pytest+marks+80% cov), wired to
    #                     .py and to the \bpytest\b keyword; also cited a
    #                     non-existent "tdd-guide" agent.
    #   git-workflow.md → git-safety.md, wired to \bgit\b and .sh. Its only
    #                     DQIII8-specific line (commit attribution trailer) was
    #                     merged there; its own copy was stale ("Sonnet 4.6") and
    #                     it linked a development-workflow.md that never existed.
    #   workflow.md     → hooks section duplicated ../rules/02_hooks_and_permissions.md,
    #                     TDD/coverage duplicated python.md, and it cited a
    #                     non-existent "planner" agent. Rest was generic web-app
    #                     patterns (Repository, API envelope) unrelated to DQIII8.
    # "performance" alias + common/performance.md removed 2026-08-17 (audit gap 9):
    # orphaned (no tool/keyword mapping referenced it) AND generic Claude Code
    # boilerplate, not DQIII8 content — it redefined tiers with a numeric 1/2/3
    # competing taxonomy. La taxonomía canónica es C/B/B+/B++/A/S y vive en
    # ../rules/03_tiering_and_routing.md (alias "tiering"). No redefinir tiers aquí.
}

# ── ALWAYS injected (ops guard + core behavior, ~1.040 tokens combined) ──────
_ALWAYS: tuple[str, ...] = ("ops", "core-behavior")  # prohibitions + autonomy + zero-complacency/cost-first

# ── Tool → rules mapping ─────────────────────────────────────────────────────
# Each entry is a list of rule aliases to inject.
# Bash rules additionally filtered by command keyword below.
_TOOL_RULES: dict[str, list[str]] = {
    "Bash":       [],                        # resolved dynamically from command
    "Edit":       [],                        # resolved dynamically from file_path
    "Write":      [],                        # resolved dynamically from file_path
    "Read":       ["prevention"],
    "Glob":       [],
    "Grep":       [],
    "Agent":      ["tiering", "agents"],     # tiering replaces legacy routing
    "WebFetch":   ["web-tools"],
    "WebSearch":  ["web-tools"],
    "TodoWrite":  [],
    "TodoRead":   [],
}

# ── Bash keyword → rules ─────────────────────────────────────────────────────
_BASH_KEYWORD_RULES: list[tuple[re.Pattern, list[str]]] = [
    (re.compile(r"\bgit\b"),                        ["git-safety", "prevention"]),
    (re.compile(r"\bpython3?\b|\bpytest\b|\bpip\b"), ["python"]),
    # sqlite3 commands → inject full DB mutation rules
    (re.compile(r"\bsqlite3\b"),                    ["db-mutations", "prevention"]),
    # schema migration commands
    (re.compile(r"apply_migrations|schema_v2"),     ["db-mutations"]),
    (re.compile(r"\bsystemctl\b|\bservice\b"),       ["prevention"]),
    (re.compile(r"\bnohup\b|\bbg\b"),               []),
    (re.compile(r"\bclaude\b|\bcc\b"),               ["tools"]),
    (re.compile(r"\bagent\b|\borchestrat"),          ["tiering", "agents", "plan-gate"]),
    (re.compile(r"\btmux\b|\byazi\b|bin/workspace|launch_(swarm|beeswarm|monitor)"), ["workspace"]),
    (re.compile(r"generate_company|save_response|intl.writer|intl.reports"), ["intl-reports"]),
    (re.compile(r"\bfirecrawl\b"),                   ["web-tools"]),
]

# ── File extension → rules ───────────────────────────────────────────────────
_EXT_RULES: dict[str, list[str]] = {
    ".py":   ["python", "quality"],
    ".md":   ["ops"],
    ".json": [],
    ".sql":  ["db-mutations", "prevention"],  # SQL edits always get DB mutation rules
    ".sh":   ["git-safety"],
    ".toml": [],
    ".yaml": [],
    ".yml":  [],
}


def _read(alias: str) -> str:
    """Read rule file content; return empty string on any error.

    Fail-open by contract (hook errors must degrade to APPROVE), but emit a
    degraded-signal warning to stderr so missing/broken rule files are visible
    in hook logs instead of silently injecting nothing (audit P3-15, 2026-07-05).
    """
    rel = _REGISTRY.get(alias, "")
    if not rel:
        print(f"[rules_dispatcher] WARN: unknown rule alias '{alias}'", file=sys.stderr)
        return ""
    path = RULES_DB / rel
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception as exc:
        print(
            f"[rules_dispatcher] WARN: rule file unreadable for alias "
            f"'{alias}' ({path}): {exc.__class__.__name__}",
            file=sys.stderr,
        )
        return ""


def get_rules(tool: str, tool_input: dict) -> str:
    """Return concatenated relevant rules for this tool call.

    Args:
        tool:       Claude Code tool name (e.g. "Bash", "Edit")
        tool_input: The tool's input dict from the hook payload

    Returns:
        A string block ready to inject as additionalContext, or "" if nothing relevant.
    """
    aliases: list[str] = list(_ALWAYS)  # start with always-injected set

    # ── Tool-specific rules ───────────────────────────────────────────────────
    base = _TOOL_RULES.get(tool, [])
    aliases.extend(base)

    # ── Bash: inspect the command ─────────────────────────────────────────────
    if tool == "Bash":
        cmd = tool_input.get("command", "")
        for pattern, rule_list in _BASH_KEYWORD_RULES:
            if pattern.search(cmd):
                aliases.extend(rule_list)

    # ── Edit / Write: inspect the file path ──────────────────────────────────
    elif tool in ("Edit", "Write"):
        path = tool_input.get("file_path", "")
        ext = Path(path).suffix.lower()
        aliases.extend(_EXT_RULES.get(ext, []))
        # Path-specific deterministic module injection
        if ".claude/hooks" in path:
            aliases.extend(["hooks-perms"])
        if "openrouter_wrapper" in path or "director.py" in path or "domain_agent" in path:
            aliases.extend(["tiering"])
        if "database/" in path or path.endswith(".sql"):
            aliases.extend(["db-mutations"])

    # ── Deduplicate preserving order ─────────────────────────────────────────
    seen: set[str] = set()
    unique: list[str] = []
    for a in aliases:
        if a not in seen and a in _REGISTRY:
            seen.add(a)
            unique.append(a)

    if not unique:
        return ""

    # ── Build injection block ─────────────────────────────────────────────────
    parts: list[str] = ["[DQIII8 Rules — context-specific]"]
    for alias in unique:
        content = _read(alias)
        if content:
            parts.append(content)

    if len(parts) == 1:
        return ""

    return "\n\n".join(parts)


_ENCODING = None


def token_estimate(text: str) -> int:
    """Real cl100k_base token count (tiktoken). Falls back to the word-count
    heuristic only if tiktoken/its encoding data is unavailable — that
    heuristic undercounts real BPE tokens by ~30-40% on this corpus and must
    never be the source of a number cited in docs (RC8, 2026-08-17/18)."""
    global _ENCODING
    if _ENCODING is None:
        try:
            import tiktoken

            _ENCODING = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _ENCODING = False
    if _ENCODING is False:
        return round(len(text.split()) / 0.75)
    return len(_ENCODING.encode(text))
