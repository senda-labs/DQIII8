"""
DQIII8 — Rules Dispatcher (RAG de Reglas Dinámico)
Inyecta SÓLO las reglas relevantes al contexto del tool en curso.

En lugar de cargar el corpus de reglas entero en cada turno, este módulo mapea
tool + input → subconjunto mínimo de reglas (~1211–9203 tokens, cl100k_base real).
El número de archivos del registro no se cita aquí: el recuento vivo es
`len(_REGISTRY)` y su parte de rules_db/ está fijada en CLAUDE.md
("Contextual rules (N)"), validada por check_claude_md_counts().

RANGO CANÓNICO (medido con token_estimate(), cl100k_base real vía tiktoken):
**suelo 1211** (solo _ALWAYS = ops + core-behavior), **techo 9203**. Suelo de
sesión 2591 (suelo + CLAUDE.md, el único fichero que Claude Code auto-inyecta en
toda sesión) — re-medido 2026-09-11. Valores anteriores (828/6080/1683,
publicados 2026-09-10) llevaban semanas desactualizados sin que
validate_rules_registry.py lo detectara: su check de presupuesto de tokens
dependía de `python3 -m pip show tiktoken` en el intérprete que de verdad
ejecuta el hook (run.sh) y el pre-commit (`command -v python3`), y ese
intérprete del sistema no tenía tiktoken instalado — el check caía al
fallback de estimación por palabras, cuyo propio comentario advierte que
"nunca debe ser la fuente de un número citado en docs", y pasaba en verde
sin comparar nada real. Fix 2026-09-11: `pip install --break-system-packages
tiktoken` en el intérprete de sistema (sin tocar run.sh ni
.git/hooks/pre-commit, que ya resuelven a ese intérprete). Auditoría
completa: docs/plglobal/README.md, ronda 2026-09-11c.
Un intento anterior de repúblicar estos números el 2026-09-08
invirtió los valores (publicó cifras más altas que no correspondían a
ninguna medición real) — detectado por validate_rules_registry.py antes de
comitear, revertido a los valores medidos correctamente.
Cualquier añadido a un fichero inyectado obliga a repetir esta medida.

El techo es el MÁXIMO REALMENTE ALCANZABLE, no el peor caso de la matriz
representativa: un Bash que combina todas las keywords de _BASH_KEYWORD_RULES
en un mismo comando. La otra rama alta es Edit sobre .claude/hooks/**.py, por
debajo de ese techo. Publicar el peor caso de la matriz deja fuera ambas.

RE-MEDIR OBLIGATORIAMENTE siempre que cambie de tamaño 00_core_behavior.md,
dqiii8-ops.md, o cualquier fichero de rules_db/ o rules/ que esté en _ALWAYS o
en un trigger, y siempre que se añada/quite un trigger. Un solo sitio cita el
rango: este docstring (CLAUDE.md solo referencia el mecanismo, no los números).
02_hooks_and_permissions.md NO debe citar los números — apunta aquí
(invariante verificada por bin/tools/validate_rules_registry.py, que además
mide el suelo y los techos reales en cada commit).

DEDUP POR SESIÓN: los números de arriba son POR LLAMADA. pre_tool_use.py
llama a get_rules() en cada tool call, así que sin dedup el coste acumulado
de una sesión es techo x N. Desde 2026-08-20 cada alias se inyecta como
máximo una vez por sesión (estado en var/rules_injected/<CLAUDE_SESSION_ID>,
en disco porque cada hook es un subproceso nuevo). El dedup se DESACTIVA con
DQIII8_RULES_DEDUP=0 (lo pone la fixture autouse de tests/conftest.py) o si
CLAUDE_SESSION_ID no está definido (validate_rules_registry.py). Ambos siguen
midiendo el suelo/techo real por llamada; el rango canónico no cambia.

Las reglas contextuales residen en .claude/rules_db/ y en .claude/rules/*.md
(salvo 00_core_behavior.md, en _ALWAYS), fuera del auto-inject de Claude Code:
este dispatcher las carga bajo demanda, una por alias, disparada por tool/
comando/extensión — nunca el fichero de reglas entero de una tacada. Ningún
fichero de rules/ ni rules_db/ se auto-inyecta por sí mismo; CLAUDE.md es el
único auto-inyectado por Claude Code, y es deliberadamente distinto (metodología
estática, no reglas dinámicas).
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Sequence

# Resolved from this file's own location, not DQIII8_ROOT: a worktree-isolated
# subagent never gets DQIII8_ROOT exported into its env (subagent_start.py
# creates the worktree but doesn't set it), so an env-var-based path silently
# pointed every worktree agent's rules lookup back at the main tree's rules_db.
RULES_DB = Path(__file__).resolve().parent.parent / "rules_db"

# ── Rule file registry ────────────────────────────────────────────────────────
# Paths are relative to RULES_DB; "../rules/" reaches the deterministic modules.
_REGISTRY: dict[str, str] = {
    # ── Deterministic modules (new rule engine split) ─────────────────────────
    "core-behavior": "../rules/00_core_behavior.md",
    "db-mutations": "../rules/01_database_mutations.md",
    "hooks-perms": "../rules/02_hooks_and_permissions.md",
    "tiering": "../rules/03_tiering_and_routing.md",
    # ── Legacy contextual rules (rules_db/) ───────────────────────────────────
    "git-safety": "git-safety.md",
    "python": "python.md",
    "ops": "dqiii8-ops.md",
    "prevention": "dqiii8-error-prevention.md",
    "tools": "dqiii8-tools.md",
    "plan-gate": "dqiii8-plan-gate.md",
    "workspace": "workspace.md",
    "intl-reports": "intl-reports-ops.md",
    "speckit": "dqiii8-speckit.md",
    "web-tools": "web-research-tools.md",
    "agents": "common/agents.md",
    "quality": "common/quality.md",
    # La taxonomía de tiers canónica es C/B/B+/B++/A/S y vive en
    # ../rules/03_tiering_and_routing.md (alias "tiering"). No redefinir tiers aquí.
}

# ── ALWAYS injected (ops guard + core behavior) ──────────────────────────────
# Estos dos ficheros son el suelo de tokens declarado en el docstring.
_ALWAYS: tuple[str, ...] = (
    "ops",
    "core-behavior",
)  # prohibitions + autonomy + zero-complacency/cost-first

# ── Tool → rules mapping ─────────────────────────────────────────────────────
# Bash rules additionally filtered by command keyword below.
_TOOL_RULES: dict[str, list[str]] = {
    "Bash": [],  # resolved dynamically from command
    "Edit": [],  # resolved dynamically from file_path
    "Write": [],  # resolved dynamically from file_path
    "Read": ["prevention"],
    "Glob": [],
    "Grep": [],
    "Agent": ["tiering", "agents"],
    "WebFetch": ["web-tools"],
    "WebSearch": ["web-tools"],
    "TodoWrite": [],
    "TodoRead": [],
}

# ── Bash keyword → rules ─────────────────────────────────────────────────────
_BASH_KEYWORD_RULES: list[tuple[re.Pattern, list[str]]] = [
    (re.compile(r"\bgit\b"), ["git-safety", "prevention"]),
    (re.compile(r"\bpython3?\b|\bpytest\b|\bpip\b"), ["python"]),
    # sqlite3 commands → inject full DB mutation rules
    (re.compile(r"\bsqlite3\b"), ["db-mutations", "prevention"]),
    # schema migration commands
    (re.compile(r"apply_migrations|schema_v2"), ["db-mutations"]),
    (re.compile(r"\bsystemctl\b|\bservice\b"), ["prevention"]),
    (re.compile(r"(?<![./])\bclaude\b"), ["tools"]),
    (re.compile(r"bin/agents|bin/core/dispatch|\borchestrat"), ["tiering", "agents", "plan-gate"]),
    (re.compile(r"\btmux\b|\byazi\b|bin/workspace|launch_(swarm|beeswarm|monitor)"), ["workspace"]),
    (re.compile(r"generate_company|save_response|intl.writer|intl.reports"), ["intl-reports"]),
    (re.compile(r"\bfirecrawl\b"), ["web-tools"]),
    (re.compile(r"speckit|spec-kit|specify\b"), ["speckit"]),
]

# ── File extension → rules ───────────────────────────────────────────────────
_EXT_RULES: dict[str, list[str]] = {
    ".py": ["python", "quality"],
    ".md": [],
    ".json": [],
    ".sql": ["db-mutations", "prevention"],  # SQL edits always get DB mutation rules
    ".sh": ["git-safety"],
    ".toml": [],
    ".yaml": [],
    ".yml": [],
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


# ── Per-session injection state ──────────────────────────────────────────────
# On disk, not in memory: every hook invocation is a fresh subprocess, so
# nothing one call sets is visible to the next.
_STATE_DIR = Path(__file__).resolve().parent.parent.parent / "var" / "rules_injected"


def _state_file(session_id: str = "") -> Path | None:
    """This session's state file, or None when dedup must not apply.

    session_id should be the real id from the hook's stdin payload (see
    get_rules()); the CLAUDE_SESSION_ID env var is never populated by Claude
    Code itself (see precompact.py/postcompact.py) and is kept only as a
    fallback for direct/test invocation of this module.

    2026-09-12 fix: sanitized via the shared core.paths.safe_session_id
    (untrusted stdin value) instead of an inline regex — this module had
    silently kept its own fourth copy of a pattern paths.py's docstring
    already documented as consolidated from three ("precompact.py,
    postcompact.py, user_prompt_submit.py"). No live traversal was
    reproducible (a fixed ".txt" suffix always follows, so the path
    component can never be exactly "." or ".."), but the inline version had
    no length cap, unlike safe_session_id's max_len=128 default — an
    oversized session_id (tested live at 500 chars) produced an
    equally-long filename, risking ENAMETOOLONG on typical filesystems
    (NAME_MAX=255). _injected_this_session()/_record_injected() already
    catch OSError and fail open, so the blast radius was graceful
    degradation, not a crash — fixed anyway for consistency with the other
    three hooks and to close the length gap at the source.
    """
    if os.environ.get("DQIII8_RULES_DEDUP", "") == "0":
        return None  # explicit opt-out (tests): measure true per-call cost
    sid = (session_id or os.environ.get("CLAUDE_SESSION_ID", "")).strip()
    if not sid:
        return None  # no session identity to key state on
    # Imported lazily, not at module level: rules_registry_introspect.py's
    # load_dispatcher() execs this module's source with a synthetic __file__
    # ("<name>", no real path) for pre-commit staged-content introspection,
    # documented as relying on the module having "no import-time side
    # effects" — a module-level sys.path mutation off Path(__file__) would
    # break under that synthetic __file__. This function is never called
    # during that introspection, so the import is safe here.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "bin"))
    from core.paths import safe_session_id  # noqa: PLC0415

    return _STATE_DIR / f"{safe_session_id(sid)}.txt"


def _injected_this_session(session_id: str = "") -> set[str]:
    """Aliases already injected. Fails open to empty (= inject everything)."""
    f = _state_file(session_id)
    if f is None:
        return set()
    try:
        return set(f.read_text(encoding="utf-8").split())
    except OSError:
        return set()


def _record_injected(aliases: Sequence[str], session_id: str = "") -> None:
    """Append aliases to this session's state. Best-effort by contract."""
    f = _state_file(session_id)
    if f is None or not aliases:
        return
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        with f.open("a", encoding="utf-8") as fh:
            fh.write("".join(f"{a}\n" for a in aliases))
    except OSError as exc:
        print(
            f"[rules_dispatcher] WARN: cannot record injected rules "
            f"({f}): {exc.__class__.__name__}",
            file=sys.stderr,
        )


def get_rules(tool: str, tool_input: dict, session_id: str = "") -> str:
    """Return concatenated relevant rules for this tool call.

    Args:
        tool:       Claude Code tool name (e.g. "Bash", "Edit")
        tool_input: The tool's input dict from the hook payload

    Returns:
        A string block ready to inject as additionalContext, or "" if nothing relevant.
    """
    aliases: list[str] = list(_ALWAYS)  # start with always-injected set

    # Nested (not module-level) so rules_registry_introspect.py's AST scan of
    # get_rules() — the sole source of the "inline aliases" reachability
    # signal — still finds these string constants; a module-level helper
    # falls outside that scan and false-positives as an orphaned alias (hit
    # live 2026-09-12 when this was first factored out to module scope).
    def _path_rules(path: str) -> list[str]:
        if not path:
            return []
        out: list[str] = list(_EXT_RULES.get(Path(path).suffix.lower(), []))
        if ".claude/hooks" in path:
            out.append("hooks-perms")
        if "openrouter_wrapper" in path or "director.py" in path or "domain_agent" in path:
            out.append("tiering")
        if "database/" in path or path.endswith(".sql"):
            out.append("db-mutations")
        return out

    # ── Tool-specific rules ───────────────────────────────────────────────────
    base = _TOOL_RULES.get(tool, [])
    aliases.extend(base)

    # ── Bash: inspect the command ─────────────────────────────────────────────
    if tool == "Bash":
        cmd = tool_input.get("command", "")
        for pattern, rule_list in _BASH_KEYWORD_RULES:
            if pattern.search(cmd):
                aliases.extend(rule_list)

    # ── Edit / Write / MultiEdit: inspect the file path ───────────────────────
    # 2026-09-12 fix: MultiEdit was missing here — a real, actively-used tool
    # (permission_analyzer.py::_candidate_paths() and post_tool_use.py both
    # already treat it identically to Edit/Write) that silently got only the
    # _ALWAYS floor instead of extension/path rules. Confirmed live: a
    # MultiEdit on .claude/hooks/pre_tool_use.py got no hooks-perms rule at
    # all, while an Edit on the same file did.
    elif tool in ("Edit", "Write", "MultiEdit"):
        aliases.extend(_path_rules(tool_input.get("file_path", "")))

    # ── mcp__filesystem__ write tools: same path-based rules as Edit/Write ────
    # 2026-09-12 fix: mcp__filesystem__* is allow-listed in settings.json and
    # permission_analyzer.py's _candidate_paths() already treats write_file/
    # edit_file/move_file as write-capable for BLOCKED_PATHS/GOVERNANCE_PATHS
    # enforcement (that security decision was never affected) — but this
    # dispatcher never looked at these tools at all, so an edit to
    # .claude/hooks/*.py made via mcp__filesystem__write_file/edit_file got no
    # hooks-perms/python/quality context, unlike the identical edit made via
    # Edit. Confirmed live: mcp__filesystem__write_file on
    # .claude/hooks/pre_tool_use.py got only the _ALWAYS floor (4602 chars)
    # vs Edit's 22380. Read-only filesystem tools (read_file, list_directory,
    # ...) are deliberately not matched here — no write is happening, so no
    # write-guidance rule is missing.
    elif tool in ("mcp__filesystem__write_file", "mcp__filesystem__edit_file"):
        aliases.extend(_path_rules(tool_input.get("path", "")))

    elif tool == "mcp__filesystem__move_file":
        aliases.extend(_path_rules(tool_input.get("source", "")))
        aliases.extend(_path_rules(tool_input.get("destination", "")))

    # ── MCP dqiii8-db: same production-DB write surface as raw sqlite3 ───────
    elif tool.startswith("mcp__dqiii8-db"):
        aliases.extend(["db-mutations", "prevention"])

    # ── Deduplicate preserving order ─────────────────────────────────────────
    seen: set[str] = set()
    unique: list[str] = []
    for a in aliases:
        if a not in seen and a in _REGISTRY:
            seen.add(a)
            unique.append(a)

    already = _injected_this_session(session_id)
    unique = [a for a in unique if a not in already]

    if not unique:
        return ""

    # ── Build injection block ─────────────────────────────────────────────────
    parts: list[str] = ["[DQIII8 Rules — context-specific]"]
    emitted: list[str] = []
    for alias in unique:
        content = _read(alias)
        if content:
            parts.append(content)
            # only mark what actually carried content, so an unreadable
            # rule file is retried on the next call instead of lost
            emitted.append(alias)

    if len(parts) == 1:
        return ""

    _record_injected(emitted, session_id)
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
