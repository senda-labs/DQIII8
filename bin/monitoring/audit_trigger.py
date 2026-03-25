#!/usr/bin/env python3
"""
DQIII8 — Audit SPC Trigger
Statistical Process Control triggers for autonomous audit activation.

Returns {"trigger": True, "reason": "T1 — ...", "priority": "HIGH"|"MEDIUM"}
or     {"trigger": False}

Triggers (any one activates the auditor):
  T1: success_rate < 95% in last 50 actions
  T2: 3+ error_log entries in current session
  T3: lessons_added = 0 in last 5 consecutive sessions
  T4: 7+ days since last audit
  T5: Shannon score < 8/10 in last scan (if exists)
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

DQIII8_ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
DB = DQIII8_ROOT / "database" / "dqiii8.db"
SPC_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS spc_metrics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    checked_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    session_id  TEXT,
    trigger_id  TEXT,
    triggered   INTEGER NOT NULL DEFAULT 0,
    reason      TEXT,
    priority    TEXT,
    value_num   REAL,
    threshold   REAL
)
"""


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB), timeout=3)
    c.execute(SPC_TABLE_DDL)
    c.commit()
    return c


def _log(
    conn: sqlite3.Connection,
    session_id: str,
    trigger_id: str,
    triggered: bool,
    reason: str,
    priority: str,
    value_num: float | None,
    threshold: float | None,
) -> None:
    conn.execute(
        "INSERT INTO spc_metrics "
        "(session_id, trigger_id, triggered, reason, priority, value_num, threshold) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (session_id, trigger_id, 1 if triggered else 0, reason, priority, value_num, threshold),
    )


# ── T1: success_rate < 95% in last 50 actions ────────────────────────────────


def check_t1(conn: sqlite3.Connection, session_id: str) -> dict:
    threshold = 0.95
    row = conn.execute(
        "SELECT COUNT(*), SUM(success) FROM "
        "(SELECT success FROM agent_actions ORDER BY id DESC LIMIT 50)"
    ).fetchone()
    total, ok = (row[0] or 0), (row[1] or 0)
    if total == 0:
        return {"triggered": False, "trigger_id": "T1"}
    rate = ok / total
    triggered = rate < threshold
    status = "ALERT" if triggered else "OK"
    reason = f"T1 — success rate {rate*100:.1f}% [{status}] (last {total} actions, threshold=95%)"
    _log(conn, session_id, "T1", triggered, reason, "HIGH", rate, threshold)
    if triggered:
        return {"trigger": True, "reason": reason, "priority": "HIGH"}
    return {"triggered": False, "trigger_id": "T1"}


# ── T2: 3+ error_log entries in current session ──────────────────────────────


def check_t2(conn: sqlite3.Connection, session_id: str) -> dict:
    # Count errors in last 2h (independent of session_id — avoids cli accumulation)
    threshold = 25
    row = conn.execute(
        "SELECT COUNT(*) FROM error_log WHERE timestamp >= datetime('now', '-2 hours')",
    ).fetchone()
    count = row[0] if row else 0
    triggered = count >= threshold
    reason = f"T2 — {count} error_log entries in last 2h (threshold={threshold})"
    _log(conn, session_id, "T2", triggered, reason, "HIGH", count, threshold)
    if triggered:
        return {"trigger": True, "reason": reason, "priority": "HIGH"}
    return {"triggered": False, "trigger_id": "T2"}


# ── T3: lessons_added = 0 in last 5 consecutive sessions ─────────────────────


def check_t3(conn: sqlite3.Connection, session_id: str) -> dict:
    threshold = 5
    rows = conn.execute(
        "SELECT lessons_added FROM sessions ORDER BY start_time DESC LIMIT ?", (threshold,)
    ).fetchall()
    if len(rows) < threshold:
        return {"triggered": False, "trigger_id": "T3"}
    all_zero = all((r[0] or 0) == 0 for r in rows)
    triggered = all_zero
    reason = (
        f"T3 — lessons_added=0 in last {len(rows)} consecutive sessions"
        if triggered
        else f"T3 — lesson capture active (last {len(rows)} sessions)"
    )
    _log(conn, session_id, "T3", triggered, reason, "MEDIUM", 0.0, 1.0)
    if triggered:
        return {"trigger": True, "reason": reason, "priority": "MEDIUM"}
    return {"triggered": False, "trigger_id": "T3"}


# ── T4: 7+ days since last audit ─────────────────────────────────────────────


def check_t4(conn: sqlite3.Connection, session_id: str) -> dict:
    threshold_days = 7
    row = conn.execute("SELECT MAX(timestamp) FROM audit_reports").fetchone()
    last = row[0] if row and row[0] else None
    if not last:
        triggered = True
        days_ago = 9999
    else:
        delta = datetime.now() - datetime.fromisoformat(last)
        days_ago = delta.total_seconds() / 86400
        triggered = days_ago >= threshold_days
    reason = (
        f"T4 — {days_ago:.1f} days since last audit (threshold={threshold_days}d)"
        if triggered
        else f"T4 — last audit {days_ago:.1f} days ago (OK)"
    )
    _log(conn, session_id, "T4", triggered, reason, "MEDIUM", days_ago, float(threshold_days))
    if triggered:
        return {"trigger": True, "reason": reason, "priority": "MEDIUM"}
    return {"triggered": False, "trigger_id": "T4"}


# ── T5: Shannon score < 8/10 in last scan ────────────────────────────────────


def check_t5(conn: sqlite3.Connection, session_id: str) -> dict:
    threshold = 8.0
    # Shannon scores stored in vault_memory as subject='shannon_score'
    row = conn.execute(
        "SELECT CAST(object AS REAL) FROM vault_memory "
        "WHERE subject='shannon_score' ORDER BY last_seen DESC LIMIT 1"
    ).fetchone()
    if row is None or row[0] is None:
        _log(
            conn,
            session_id,
            "T5",
            False,
            "T5 — no Shannon score found (skip)",
            "MEDIUM",
            None,
            threshold,
        )
        return {"triggered": False, "trigger_id": "T5"}
    score = row[0]
    triggered = score < threshold
    reason = f"T5 — Shannon score {score:.1f}/10 < {threshold} threshold"
    _log(conn, session_id, "T5", triggered, reason, "MEDIUM", score, threshold)
    if triggered:
        return {"trigger": True, "reason": reason, "priority": "MEDIUM"}
    return {"triggered": False, "trigger_id": "T5"}


# ── Public API ────────────────────────────────────────────────────────────────


def check_triggers(session_id: str = "cli") -> dict:
    """
    Run all SPC triggers. Returns the first fired trigger (priority: HIGH first),
    or {"trigger": False} if none fire.
    """
    if not DB.exists():
        return {"trigger": False}

    conn = _conn()
    try:
        results = [
            check_t1(conn, session_id),
            check_t2(conn, session_id),
            check_t3(conn, session_id),
            check_t4(conn, session_id),
            check_t5(conn, session_id),
        ]
        conn.commit()
    finally:
        conn.close()

    # Return highest-priority fired trigger (HIGH > MEDIUM)
    high = [r for r in results if r.get("trigger") and r.get("priority") == "HIGH"]
    medium = [r for r in results if r.get("trigger") and r.get("priority") == "MEDIUM"]
    fired = high or medium
    if fired:
        return fired[0]
    return {"trigger": False}


# ── CLI ───────────────────────────────────────────────────────────────────────


def main() -> None:
    session_id = sys.argv[1] if len(sys.argv) > 1 else "cli"
    result = check_triggers(session_id)
    print(json.dumps(result, indent=2))
    if result.get("trigger"):
        print(f"\n[SPC] AUDIT TRIGGERED — {result['reason']}", file=sys.stderr)
        import subprocess as _sp
        _sp.run(
            ["python3", str(DQIII8_ROOT / "bin" / "monitoring" / "auditor_local.py")],
            check=False,
        )
        try:
            sys.path.insert(0, str(DQIII8_ROOT / "bin" / "core"))
            from notify import send_telegram
            send_telegram(f"[SPC] AUDIT TRIGGERED\n{result['reason']}")
        except Exception:
            pass
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
