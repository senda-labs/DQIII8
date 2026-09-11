#!/usr/bin/env python3
"""
DQIII8 Hook — PostCompact
Re-injects the minimum operational baseline after context compaction.

Fires AFTER context-mode finishes compaction.
Restores: active model, active project, next step, audit score (only if
pending), recent-activity resume snippet (only if any agent_actions rows
exist for this session) — see "Injection rules" comment below. Reads the
session-scoped tasks/precompact_state_{session_id}.json written by
precompact.py to recover previous state, then deletes it. Always exits
0 — never abort.
"""

import json
import logging
import logging.handlers
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
DB = ROOT_DIR / "database" / "dqiii8.db"

# Rango 2 fix (2026-08-19 red-team audit) — mirrors precompact.py's
# per-session state file. The lookup key MUST come from this hook's own
# stdin session_id, never from the state file's own recorded session_id —
# trusting the file's content to find itself is exactly how the old shared
# tasks/precompact_state.json leaked one session's state into another's.
# Sanitizer shared via core.paths.safe_session_id (was a duplicate regex).
sys.path.insert(0, str(ROOT_DIR / "bin"))
from core.paths import safe_session_id


def _state_file_for(session_id: str) -> Path:
    return ROOT_DIR / "tasks" / f"precompact_state_{safe_session_id(session_id)}.json"


_log = logging.getLogger("dqiii8.postcompact")
if not _log.handlers:
    _log.setLevel(logging.DEBUG)
    _log_dir = Path("/var/log/dqiii8")
    if _log_dir.exists():
        _fh = logging.handlers.RotatingFileHandler(
            str(_log_dir / "hooks.log"), maxBytes=2_000_000, backupCount=3
        )
        _fh.setFormatter(logging.Formatter("%(asctime)s [postcompact] %(levelname)s %(message)s"))
        _log.addHandler(_fh)
    else:
        _log.addHandler(logging.NullHandler())

try:
    data = json.load(sys.stdin)
except Exception:
    data = {}

# ── Session id — from THIS hook's own stdin (same pattern as
# session_start.py / subagent_start.py / precompact.py), needed BEFORE
# we can locate the session-scoped state file below. Deriving it from
# the state file's own contents instead — as this hook used to do — is
# exactly what let one session's PostCompact read another's state.
session_id = data.get("session_id", os.environ.get("CLAUDE_SESSION_ID", "?"))
STATE_FILE = _state_file_for(session_id)

# ── Recover pre-compact state ────────────────────────────────────────
pre_state: dict = {}
try:
    if STATE_FILE.exists():
        pre_state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        # Best-effort cleanup: this file's only reader is this hook, and
        # it has just been read — leaving it around only accumulates one
        # stale file per compact event, forever, in tasks/.
        try:
            STATE_FILE.unlink()
        except OSError:
            pass
except Exception as e:
    _log.warning("pre-compact state unreadable: %s", e)

# ── Active project ───────────────────────────────────────────────────
# DQIII8_PROJECT env var has no writer — resolve via the DB-backed SSOT instead.
try:
    from core.action_log import resolve_project_safe

    project = (
        pre_state.get("project")
        or resolve_project_safe(session_id, cwd=data.get("cwd"))
        or "dqiii8-core"
    )
except Exception:
    project = pre_state.get("project") or "dqiii8-core"

# ── Active model ─────────────────────────────────────────────────────
model = os.environ.get("DQIII8_MODEL", "claude-sonnet-5")

# ── Latest audit score — ONLY IF an audit is pending (a score with
# nothing pending isn't actionable right after a compact) ─────────────
AUDIT_FLAG = ROOT_DIR / "tasks" / "audit_pending.flag"
audit_info = ""
if AUDIT_FLAG.exists():
    try:
        if DB.exists():
            conn = sqlite3.connect(str(DB), timeout=2)
            row = conn.execute(
                "SELECT timestamp, overall_score FROM audit_reports "
                "ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
            conn.close()
            if row:
                audit_info = f"\nAudit  : {row[0][:10]} | Score: {row[1]}/100 — pending, run /audit"
    except Exception as e:
        _log.warning("audit-score DB failed: %s", e)

# ── Project next step ────────────────────────────────────────────────
# Rango 8 fix (2026-08-19 red-team audit): same path bug as session_start.py
# — ROOT_DIR/"projects"/<x>.md never existed; real docs are at
# my-projects/<slug>/PROJECT.md.
next_step = "Not defined"
pm = ROOT_DIR / "my-projects" / project / "PROJECT.md"
try:
    if pm.exists():
        lines = pm.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if "Next step" in line:
                if i + 1 < len(lines) and lines[i + 1].strip():
                    next_step = lines[i + 1].strip()
                break
    elif project != "dqiii8-core":
        _log.warning("postcompact: PROJECT.md not found at %s", pm)
except Exception as e:
    _log.debug("next-step unreadable: %s", e)

# ── Session stats before compact ─────────────────────────────────────
actions_before = pre_state.get("actions_count", "?")

# ── Recent-activity resume snippet (Rango 9 fix) ───────────────────────
resume_snippet = pre_state.get("resume_snippet", "")
resume_block = f"\nRecent activity:\n{resume_snippet}" if resume_snippet else ""

# ── Compact hint heuristic ────────────────────────────────────────────
compact_hint = ""
try:
    n = int(actions_before)
    if n > 100:
        compact_hint = f"\n[COMPACT] Sesión muy larga ({n} acciones) — /compact recomendado"
    elif n > 50:
        compact_hint = f"\n[COMPACT] Sesión larga ({n} acciones) — considerar /compact"
except (ValueError, TypeError):
    pass

# ── Injection rules (exact, by necessity) ─────────────────────────────
# model, project, next_step : ALWAYS (minimum operational baseline)
# audit_info                : ONLY IF tasks/audit_pending.flag exists
# compact_hint               : ONLY IF actions_before > 50 (already conditional)
# resume_block               : ONLY IF precompact.py found agent_actions rows
#                               for this session (Rango 9 replacement for the
#                               retired context-mode continuity snapshot —
#                               see precompact.py's resume_snippet comment)
ctx = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DQIII8 — PostCompact
Context compacted — state restored
Model  : {model}
Project: {project}
Next   : {next_step}{audit_info}
Session actions: {actions_before}{compact_hint}{resume_block}
Compacted : {datetime.now().strftime('%Y-%m-%d %H:%M')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

_log.info(
    "injected session=%s audit=%s hint=%s chars=%d",
    session_id,
    bool(audit_info),
    bool(compact_hint),
    len(ctx),
)
print(json.dumps({"additionalContext": ctx}))
sys.exit(0)
