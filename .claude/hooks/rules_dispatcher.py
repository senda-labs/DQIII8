"""
DQIII8 — Rules Dispatcher (RAG de Reglas Dinámico)
Inyecta SÓLO las reglas relevantes al contexto del tool en curso.

En lugar de cargar los 16 archivos en cada turno (~4k tokens), este módulo
mapea tool + input → subconjunto mínimo de reglas (~200-800 tokens).

Las reglas residen en .claude/rules_db/ (fuera del auto-inject de Claude Code).
El único archivo en .claude/rules/ es el DYNAMIC.md de 3 líneas.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Sequence

RULES_DB = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8")) / ".claude" / "rules_db"

# ── Rule file registry ────────────────────────────────────────────────────────
# Short aliases → file paths relative to rules_db/
_REGISTRY: dict[str, str] = {
    "git-safety":     "git-safety.md",
    "python":         "python.md",
    "routing":        "routing.md",
    "ops":            "dqiii8-ops.md",
    "prevention":     "dqiii8-error-prevention.md",
    "deliverables":   "dqiii8-deliverables.md",
    "tools":          "dqiii8-tools.md",
    "plan-gate":      "dqiii8-plan-gate.md",
    "context-window": "dqiii8-context-window.md",
    "workspace":      "workspace.md",
    "agents":         "common/agents.md",
    "quality":        "common/quality.md",
    "git-workflow":   "common/git-workflow.md",
    "workflow":       "common/workflow.md",
    "testing":        "common/testing.md",
    "performance":    "common/performance.md",
}

# ── ALWAYS injected (minimal ops guard, <300 tokens combined) ────────────────
_ALWAYS: tuple[str, ...] = ("ops",)          # prohibitions + autonomy rules

# ── Tool → rules mapping ─────────────────────────────────────────────────────
# Each entry is a list of rule aliases to inject.
# Bash rules additionally filtered by command keyword below.
_TOOL_RULES: dict[str, list[str]] = {
    "Bash":       [],           # resolved dynamically from command
    "Edit":       [],           # resolved dynamically from file_path
    "Write":      [],           # resolved dynamically from file_path
    "Read":       ["prevention"],
    "Glob":       [],
    "Grep":       [],
    "Agent":      ["routing", "agents"],
    "WebFetch":   [],
    "WebSearch":  [],
    "TodoWrite":  [],
    "TodoRead":   [],
}

# ── Bash keyword → rules ─────────────────────────────────────────────────────
_BASH_KEYWORD_RULES: list[tuple[re.Pattern, list[str]]] = [
    (re.compile(r"\bgit\b"),                       ["git-safety", "prevention"]),
    (re.compile(r"\bpython3?\b|\bpytest\b|\bpip\b"), ["python"]),
    (re.compile(r"\bsqlite3\b"),                   ["prevention"]),
    (re.compile(r"\bsystemctl\b|\bservice\b"),      ["prevention"]),
    (re.compile(r"\bnohup\b|\bbg\b|\bnohup\b"),    []),
    (re.compile(r"\bclauде\b|\bcc\b"),             ["tools"]),
    (re.compile(r"\bagent\b|\borchestrat"),         ["routing"]),
]

# ── File extension → rules ───────────────────────────────────────────────────
_EXT_RULES: dict[str, list[str]] = {
    ".py":   ["python", "quality"],
    ".md":   ["ops"],
    ".json": [],
    ".sql":  ["prevention"],
    ".sh":   ["git-safety"],
    ".toml": [],
    ".yaml": [],
    ".yml":  [],
}


def _read(alias: str) -> str:
    """Read rule file content; return empty string on any error."""
    path = RULES_DB / _REGISTRY.get(alias, "")
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
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


def token_estimate(text: str) -> int:
    """Rough token estimate (word count / 0.75)."""
    return round(len(text.split()) / 0.75)
