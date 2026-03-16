# P.C. 3 — stop.py Refactor Spec

**Status:** Ready to execute (pre-Mission Control)
**Blocked by:** Nothing — P.C.1 and P.C.2 resolved
**Priority:** Before Mission Control daemon or Telegram bot extension

---

## Why now

stop.py has 7 responsibilities in 559 lines. Mission Control will add:
- Daemon heartbeat write (step 8)
- Inactivity detection trigger (step 9)

Telegram bot will add:
- Session summary notification (step 10)

Adding to a 559-line monolith is high risk. Refactoring first gives clean insertion points.

---

## Current responsibility map

| Lines | Module target | Responsibility |
|-------|---------------|----------------|
| 23-106 | `lessons.py` | Lesson counting (3 fallbacks: HEAD diff, working tree, commit history) |
| 108-128 | `lessons.py` | Implicit vault lessons supplement (post_tool_use counter) |
| 130-181 | `instincts.py` | Instinct extraction from lessons.md diff |
| 183-273 | `vault.py` | Vault memory extraction via Claude Haiku (SPO triples) |
| 275-318 | `instincts.py` | Intelligence loop: boost/decay confidence |
| 320-359 | `sessions.py` | Session close to DB (sessions table INSERT/UPDATE) |
| 360+ | `__init__.py` | Git commit+push, audit flag, observe_events sync, handover |

---

## Target structure

```
.claude/hooks/
  stop.py              # thin orchestrator (~50 lines)
  stop/
    __init__.py        # empty or re-exports
    lessons.py         # count_lessons(session, db, jarvis_root) → int
    instincts.py       # extract_instincts(diff_result, db) + run_intelligence_loop(db)
    vault.py           # extract_vault_facts(session, db, diff_result, jarvis_root)
    sessions.py        # close_session(session, db, lessons_added, project, model) → None
    audit_trigger.py   # check_audit_flag(db, jarvis_root) → bool
```

---

## New stop.py skeleton (~50 lines)

```python
#!/usr/bin/env python3
"""JARVIS Hook — Stop (orchestrator). Logic lives in stop/ modules."""

import sys, json, os, subprocess
from datetime import datetime
from pathlib import Path

try:
    data = json.load(sys.stdin)
except Exception:
    data = {}

session = data.get("session_id", "unknown")
JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB = JARVIS / "database" / "jarvis_metrics.db"
NOW = datetime.now().isoformat()

sys.path.insert(0, str(JARVIS / ".claude" / "hooks"))
from stop.lessons import count_lessons
from stop.instincts import extract_instincts, run_intelligence_loop
from stop.vault import extract_vault_facts
from stop.sessions import close_session
from stop.audit_trigger import check_audit_flag

# Run pipeline
diff_result, lessons_added = count_lessons(session, DB, JARVIS)
extract_instincts(diff_result, DB, NOW)
extract_vault_facts(session, DB, diff_result, JARVIS)
run_intelligence_loop(DB, NOW)
close_session(session, DB, lessons_added, JARVIS, NOW)
# ... git commit, observe_events, audit flag (stays in stop.py — side effects)
```

---

## Insertion points for future features

**Mission Control:**
```python
from stop.mission_control import write_daemon_heartbeat   # step 8 (new)
write_daemon_heartbeat(session, DB, JARVIS)
```

**Telegram bot:**
```python
from stop.notifications import send_session_summary       # step 10 (new)
send_session_summary(session, lessons_added, JARVIS)
```

---

## Rules for the refactor

1. Zero behavior change — outputs, DB writes, and timing must be identical to current stop.py
2. Each module has exactly one responsibility — no cross-imports between modules
3. All modules catch their own exceptions (same `try/except pass` pattern as today)
4. stop.py remains the only entry point — hooks system calls stop.py, not the submodules
5. Tests: run `python3 .claude/hooks/stop.py < /dev/null` before and after — confirm same output
6. Commit per module extracted (5 commits), then one final commit removing old code from stop.py

---

## Estimated scope

~6 files touched, ~560 lines reorganized (no new logic). Plan mode required (>3 files).
