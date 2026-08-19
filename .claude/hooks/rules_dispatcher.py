"""
DQIII8 — Rules Dispatcher (RAG de Reglas Dinámico)
Inyecta SÓLO las reglas relevantes al contexto del tool en curso.

En lugar de cargar el corpus de reglas entero en cada turno, este módulo mapea
tool + input → subconjunto mínimo de reglas (~1060–7741 tokens, cl100k_base real).
El número de archivos del registro no se cita aquí: el recuento vivo es
`len(_REGISTRY)` y su parte de rules_db/ está fijada en CLAUDE.md
("Contextual rules (N)"), validada por check_claude_md_counts().

RANGO CANÓNICO (medido con token_estimate(), cl100k_base real vía tiktoken):
**suelo 1060** (solo _ALWAYS = ops + core-behavior), **techo 7741**.
**suelo de sesión 2761** = ese suelo + CLAUDE.md + DYNAMIC.md, los dos ficheros que
Claude Code auto-inyecta en toda sesión; es el impuesto de contexto real por sesión.

El techo es el MÁXIMO REALMENTE ALCANZABLE, no el peor caso de la matriz
representativa: un Bash que combina todas las keywords de _BASH_KEYWORD_RULES
en un mismo comando. La otra rama alta es Edit sobre .claude/hooks/**.py, por
debajo de ese techo. Publicar el peor caso de la matriz deja fuera ambas.

RE-MEDIR OBLIGATORIAMENTE siempre que cambie de tamaño 00_core_behavior.md,
dqiii8-ops.md, o cualquier fichero de rules_db/ o rules/ que esté en _ALWAYS o
en un trigger, y siempre que se añada/quite un trigger. Solo 2 sitios citan el
rango y deben actualizarse juntos: este docstring y .claude/rules/DYNAMIC.md.
02_hooks_and_permissions.md NO debe citar los números — apunta aquí
(invariante verificada por bin/tools/validate_rules_registry.py, que además
mide el suelo y los techos reales en cada commit).

Las reglas contextuales residen en .claude/rules_db/, fuera del auto-inject de
Claude Code: este dispatcher las carga bajo demanda. El único fichero de reglas
que Claude Code auto-inyecta en el contexto de sesión es .claude/rules/DYNAMIC.md;
el resto de .claude/rules/*.md se inyecta también bajo demanda por este dispatcher.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Sequence

RULES_DB = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8")) / ".claude" / "rules_db"

# ── Rule file registry ────────────────────────────────────────────────────────
# Paths are relative to RULES_DB; "../rules/" reaches the deterministic modules.
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
    "workspace":      "workspace.md",
    "intl-reports":   "intl-reports-ops.md",
    "web-tools":      "web-research-tools.md",
    "agents":         "common/agents.md",
    "quality":        "common/quality.md",
    # La taxonomía de tiers canónica es C/B/B+/B++/A/S y vive en
    # ../rules/03_tiering_and_routing.md (alias "tiering"). No redefinir tiers aquí.
}

# ── ALWAYS injected (ops guard + core behavior) ──────────────────────────────
# Estos dos ficheros son el suelo de tokens declarado en el docstring.
_ALWAYS: tuple[str, ...] = ("ops", "core-behavior")  # prohibitions + autonomy + zero-complacency/cost-first

# ── Tool → rules mapping ─────────────────────────────────────────────────────
# Bash rules additionally filtered by command keyword below.
_TOOL_RULES: dict[str, list[str]] = {
    "Bash":       [],                        # resolved dynamically from command
    "Edit":       [],                        # resolved dynamically from file_path
    "Write":      [],                        # resolved dynamically from file_path
    "Read":       ["prevention"],
    "Glob":       [],
    "Grep":       [],
    "Agent":      ["tiering", "agents"],
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
    (re.compile(r"\bclaude\b|\bcc\b"),               ["tools"]),
    (re.compile(r"\bagent\b|\borchestrat"),          ["tiering", "agents", "plan-gate"]),
    (re.compile(r"\btmux\b|\byazi\b|bin/workspace|launch_(swarm|beeswarm|monitor)"), ["workspace"]),
    (re.compile(r"generate_company|save_response|intl.writer|intl.reports"), ["intl-reports"]),
    (re.compile(r"\bfirecrawl\b"),                   ["web-tools"]),
]

# ── File extension → rules ───────────────────────────────────────────────────
_EXT_RULES: dict[str, list[str]] = {
    ".py":   ["python", "quality"],
    ".md":   [],
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
    in hook logs instead of silently injecting nothing.
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
    never be the source of a number cited in docs."""
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
