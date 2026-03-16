#!/usr/bin/env python3
"""
JARVIS Hook — PreCompact
Saves JARVIS-specific state before context-mode compaction runs.

Runs BEFORE context-mode/hooks/precompact.mjs (ordered by settings.json).
Does NOT replace context-mode — it is complementary.
Exit 0 always: never abort the compaction.
"""

import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB = JARVIS / "database" / "jarvis_metrics.db"
STATE_FILE = JARVIS / "tasks" / "precompact_state.json"
SESSION_ID = os.environ.get("CLAUDE_SESSION_ID", "unknown")

try:
    data = json.load(sys.stdin)
except Exception:
    data = {}

state: dict = {
    "timestamp": datetime.now().isoformat(),
    "session_id": SESSION_ID,
    "compact_trigger": data.get("trigger", "unknown"),
}

# ── Read last session stats from DB ────────────────────────────────
try:
    conn = sqlite3.connect(str(DB), timeout=3)
    row = conn.execute(
        "SELECT project, started_at FROM sessions WHERE session_id=? LIMIT 1",
        (SESSION_ID,),
    ).fetchone()
    if row:
        state["project"] = row[0]
        state["started_at"] = row[1]

    actions_row = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(tokens_used),0) FROM agent_actions " "WHERE session_id=?",
        (SESSION_ID,),
    ).fetchone()
    if actions_row:
        state["actions_count"] = actions_row[0]
        state["tokens_so_far"] = actions_row[1]

    # Increment compact_count in sessions (best-effort)
    conn.execute(
        "UPDATE sessions SET compact_count = COALESCE(compact_count,0) + 1 " "WHERE session_id=?",
        (SESSION_ID,),
    )
    conn.commit()
    conn.close()
except Exception:
    pass

# ── Write state file for post-compact recovery ─────────────────────
try:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
except Exception:
    pass

# PreCompact must output {} and exit 0 (never abort compaction)
print(json.dumps({}))
sys.exit(0)
