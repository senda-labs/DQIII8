#!/usr/bin/env python3
"""
DQIII8 Hook — PostCompact
Re-injects essential context after context compaction.

Fires AFTER context-mode finishes compaction.
Restores: active model, active project, last 3 lessons, audit score.
Reads precompact_state.json written by precompact.py to recover previous state.
Always exits 0 — never abort.
"""

import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB = JARVIS / "database" / "jarvis_metrics.db"
LESSONS = JARVIS / "tasks" / "lessons.md"
STATE_FILE = JARVIS / "tasks" / "precompact_state.json"

try:
    data = json.load(sys.stdin)
except Exception:
    data = {}

# ── Recover pre-compact state ────────────────────────────────────────
pre_state: dict = {}
try:
    if STATE_FILE.exists():
        pre_state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
except Exception:
    pass

# ── Active project ───────────────────────────────────────────────────
project = pre_state.get("project") or os.environ.get("JARVIS_PROJECT", "") or "jarvis-core"

# ── Active model ─────────────────────────────────────────────────────
model = os.environ.get("JARVIS_MODEL", "claude-sonnet-4-6")

# ── Last 3 lessons ───────────────────────────────────────────────────
lessons: list[str] = []
try:
    if LESSONS.exists():
        all_lines = LESSONS.read_text(encoding="utf-8").splitlines()
        lessons = [l for l in all_lines if l.strip().startswith("[20")][-3:]
except Exception:
    pass

# ── Latest audit score ───────────────────────────────────────────────
audit_info = "No audit"
try:
    if DB.exists():
        conn = sqlite3.connect(str(DB), timeout=2)
        row = conn.execute(
            "SELECT timestamp, overall_score FROM audit_reports " "ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if row:
            audit_info = f"{row[0][:10]} | Score: {row[1]}/100"
except Exception:
    pass

# ── Project next step ────────────────────────────────────────────────
next_step = "Not defined"
pm = JARVIS / "projects" / f"{project}.md"
try:
    if pm.exists():
        lines = pm.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if "Next step" in line:
                if i + 1 < len(lines) and lines[i + 1].strip():
                    next_step = lines[i + 1].strip()
                break
except Exception:
    pass

# ── Session stats before compact ─────────────────────────────────────
actions_before = pre_state.get("actions_count", "?")
session_id = pre_state.get("session_id", os.environ.get("CLAUDE_SESSION_ID", "?"))

ctx = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DQIII8 — PostCompact {datetime.now().strftime('%H:%M')}
Context compacted — state restored
Model  : {model}
Project: {project}
Next   : {next_step}
Audit  : {audit_info}
Session actions: {actions_before}

LAST LESSONS:
{chr(10).join(lessons) if lessons else '  (none recorded)'}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

print(json.dumps({"additionalContext": ctx}))
sys.exit(0)
