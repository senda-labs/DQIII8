#!/usr/bin/env python3
"""
DQIII8 Hook — PreCompact
Saves DQIII8-specific state before context-mode compaction runs.

Runs BEFORE context-mode/hooks/precompact.mjs (ordered by settings.json).
Does NOT replace context-mode — it is complementary.
Exit 0 always: never abort the compaction.
"""

import json
import logging
import logging.handlers
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
DB = ROOT_DIR / "database" / "dqiii8.db"

# Rango 2 fix (2026-08-19 red-team audit): a single shared state file let a
# second session's PreCompact clobber a first session's state before its own
# PostCompact read it back — cross-session context leak, confirmed live.
# Suffix by session_id (sanitized — untrusted stdin value, must not escape
# tasks/ via path traversal) so concurrent sessions never share a file.
_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_-]")


def _state_file_for(session_id: str) -> Path:
    safe_id = _SAFE_ID_RE.sub("_", session_id)[:128] or "unknown"
    return ROOT_DIR / "tasks" / f"precompact_state_{safe_id}.json"


_log = logging.getLogger("dqiii8.precompact")
if not _log.handlers:
    _log.setLevel(logging.DEBUG)
    _log_dir = Path("/var/log/dqiii8")
    if _log_dir.exists():
        _fh = logging.handlers.RotatingFileHandler(
            str(_log_dir / "hooks.log"), maxBytes=2_000_000, backupCount=3
        )
        _fh.setFormatter(logging.Formatter("%(asctime)s [precompact] %(levelname)s %(message)s"))
        _log.addHandler(_fh)
    else:
        _log.addHandler(logging.NullHandler())

try:
    data = json.load(sys.stdin)
except Exception:
    data = {}

# Claude Code passes session_id in the hook's stdin JSON, not a
# CLAUDE_SESSION_ID env var — reading the env var instead is always
# "unknown", which silently breaks the DB lookup below and the
# session-scoped project resolution postcompact.py depends on.
SESSION_ID = data.get("session_id", "unknown")
STATE_FILE = _state_file_for(SESSION_ID)

# Only session_id/project/actions_count/resume_snippet are stored: those
# are the only fields postcompact.py reads back. tokens_so_far/
# compact_trigger/started_at were computed here but never consumed —
# dropped, not "by necessity".
state: dict = {
    "session_id": SESSION_ID,
}

# ── Read last session stats from DB ────────────────────────────────
try:
    conn = sqlite3.connect(str(DB), timeout=3)
    try:
        row = conn.execute(
            "SELECT project FROM sessions WHERE session_id=? LIMIT 1",
            (SESSION_ID,),
        ).fetchone()
        if row:
            state["project"] = row[0]

        actions_row = conn.execute(
            "SELECT COUNT(*) FROM agent_actions WHERE session_id=?",
            (SESSION_ID,),
        ).fetchone()
        if actions_row:
            state["actions_count"] = actions_row[0]

        # Rango 9 fix (2026-08-19 red-team audit): context-mode's own
        # precompact.mjs built a continuity snapshot from its private,
        # non-MCP SessionDB. Retiring that hook loses that snapshot, so this
        # rebuilds an equivalent — non-MCP, Python-native — from agent_actions,
        # which post_tool_use already populates per-session throughout the
        # run (reuse before build, per Priority Ladder). This is a trail of
        # recent tool actions, not a prose summary of reasoning — that's the
        # honest ceiling of what an audit-log table can reconstruct.
        recent_rows = conn.execute(
            "SELECT tool_used, file_path FROM agent_actions "
            "WHERE session_id=? ORDER BY id DESC LIMIT 10",
            (SESSION_ID,),
        ).fetchall()
        lines = []
        for tool_used, file_path in recent_rows:
            target = (file_path or "").strip().replace("\n", " ")
            if len(target) > 100:
                target = target[:97] + "..."
            line = f"{tool_used}: {target}" if target else str(tool_used)
            if not lines or lines[-1] != line:  # collapse consecutive dupes
                lines.append(line)
        if lines:
            state["resume_snippet"] = "\n".join(reversed(lines))

        # Increment compact_count in sessions (best-effort)
        conn.execute(
            "UPDATE sessions SET compact_count = COALESCE(compact_count,0) + 1 "
            "WHERE session_id=?",
            (SESSION_ID,),
        )
        conn.commit()
    finally:
        conn.close()
except Exception as e:
    _log.warning("db-stats read failed: %s", e, exc_info=True)

# ── Write state file for post-compact recovery (atomic: temp+replace,
# so a crash mid-write never leaves postcompact.py reading a truncated
# or half-written file) ─────────────────────────────────────────────
try:
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, STATE_FILE)
except Exception as e:
    _log.warning("state-file write failed: %s", e, exc_info=True)

_log.info("state saved: %s", json.dumps(state, ensure_ascii=False))

# PreCompact must output {} and exit 0 (never abort compaction)
print(json.dumps({}))
sys.exit(0)
