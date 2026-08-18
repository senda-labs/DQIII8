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
import logging
import logging.handlers
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

JARVIS = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
DB = JARVIS / "database" / "dqiii8.db"
LESSONS = JARVIS / "tasks" / "lessons.md"
STATE_FILE = JARVIS / "tasks" / "precompact_state.json"

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

# ── Recover pre-compact state ────────────────────────────────────────
pre_state: dict = {}
try:
    if STATE_FILE.exists():
        pre_state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
except Exception as e:
    _log.warning("pre-compact state unreadable: %s", e)

# ── Session id (needed by project resolution below) ──────────────────
session_id = pre_state.get("session_id", os.environ.get("CLAUDE_SESSION_ID", "?"))

# ── Active project ───────────────────────────────────────────────────
# Opus review P2-5: DQIII8_PROJECT env var had no writer left after Stage 7
# cleanup — resolve via the DB-backed SSOT instead.
try:
    _bin_root = str(JARVIS / "bin")
    if _bin_root not in sys.path:
        sys.path.insert(0, _bin_root)
    from core.action_log import resolve_project_safe

    project = pre_state.get("project") or resolve_project_safe(session_id, cwd=data.get("cwd")) or "dqiii8-core"
except Exception:
    project = pre_state.get("project") or "dqiii8-core"

# ── Active model ─────────────────────────────────────────────────────
model = os.environ.get("DQIII8_MODEL", "claude-sonnet-5")

# ── Last 3 lessons ───────────────────────────────────────────────────
lessons: list[str] = []
try:
    if LESSONS.exists():
        all_lines = LESSONS.read_text(encoding="utf-8").splitlines()
        lessons = [l for l in all_lines if l.strip().startswith("[20")][-3:]
except Exception as e:
    _log.debug("lessons unreadable: %s", e)

# ── Latest audit score ───────────────────────────────────────────────
audit_info = "No audit"
try:
    if DB.exists():
        conn = sqlite3.connect(str(DB), timeout=2)
        row = conn.execute(
            "SELECT timestamp, overall_score FROM audit_reports "
            "ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if row:
            audit_info = f"{row[0][:10]} | Score: {row[1]}/100"
except Exception as e:
    _log.warning("audit-score DB failed: %s", e)

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
except Exception as e:
    _log.debug("next-step unreadable: %s", e)

# ── Session stats before compact ─────────────────────────────────────
actions_before = pre_state.get("actions_count", "?")

# ── Compact hint heuristic ────────────────────────────────────────────
compact_hint = ""
try:
    n = int(actions_before)
    if n > 100:
        compact_hint = (
            f"\n[COMPACT] Sesión muy larga ({n} acciones) — /compact recomendado"
        )
    elif n > 50:
        compact_hint = f"\n[COMPACT] Sesión larga ({n} acciones) — considerar /compact"
except (ValueError, TypeError):
    pass

ctx = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DQIII8 — PostCompact {datetime.now().strftime('%H:%M')}
Context compacted — state restored
Model  : {model}
Project: {project}
Next   : {next_step}
Audit  : {audit_info}
Session actions: {actions_before}{compact_hint}

LAST LESSONS:
{chr(10).join(lessons) if lessons else '  (none recorded)'}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

print(json.dumps({"additionalContext": ctx}))
sys.exit(0)
