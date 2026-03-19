"""
train_instincts.py — Trains learned_approvals from high-semantic events.

Data sources (in order of confidence):
  1. permission_decisions WHERE decision='APPROVE' → learned_approvals candidates
  2. session_events type plan_approved → reinforcement of approved patterns
  3. permission_decisions WHERE decision='DENY' → patterns to never approve (active=0)

CASS confidence decay:
  confidence = min(1.0, base + 0.05 * approvals) * (0.99 ** days_since_use)

Usage:
    python3 bin/train_instincts.py [--dry-run] [--lookback-days 30]
    (Also run via cron every 24h)
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

JARVIS_DB = Path("/root/jarvis/database/jarvis_metrics.db")

# Minimum approvals before activating a learned_approval pattern
ACTIVATION_THRESHOLD = 3

# Patterns that should NEVER be auto-approved (from critical denials)
_CRITICAL_RULE_PREFIXES = ("blocked_path", "high_risk")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(JARVIS_DB), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _decay_confidence(base: float, approvals: int, days_since_use: float) -> float:
    """CASS confidence decay: grow on approvals, decay over time."""
    grown = min(1.0, base + 0.05 * approvals)
    return round(grown * (0.99**days_since_use), 4)


def _normalize_pattern(action_detail: str | None) -> str:
    """Extract a stable, reusable pattern from action_detail."""
    if not action_detail:
        return ""
    detail = action_detail.strip()
    # For file paths: use the filename or last 2 path components
    if detail.startswith("/"):
        parts = Path(detail).parts
        return "/".join(parts[-2:]) if len(parts) >= 2 else detail
    return detail[:120]


def train_from_approvals(
    conn: sqlite3.Connection,
    lookback_days: int = 30,
    dry_run: bool = False,
) -> int:
    """
    Scan permission_decisions APPROVE entries and upsert into learned_approvals.
    Returns number of rows upserted.
    """
    since = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=lookback_days)).isoformat()

    rows = conn.execute(
        """
        SELECT tool_name, action_detail, COUNT(*) as cnt,
               MAX(timestamp) as last_seen
        FROM permission_decisions
        WHERE decision = 'APPROVE'
          AND timestamp >= ?
          AND action_detail IS NOT NULL
        GROUP BY tool_name, action_detail
        ORDER BY cnt DESC
        """,
        (since,),
    ).fetchall()

    upserted = 0
    for row in rows:
        pattern = _normalize_pattern(row["action_detail"])
        if not pattern:
            continue

        # Never learn from critical denials that were later overridden
        rule_col = conn.execute(
            "SELECT rule_triggered FROM permission_decisions "
            "WHERE tool_name=? AND action_detail=? AND decision='DENY' "
            "ORDER BY timestamp DESC LIMIT 1",
            (row["tool_name"], row["action_detail"]),
        ).fetchone()
        if rule_col and any(
            (rule_col["rule_triggered"] or "").startswith(p) for p in _CRITICAL_RULE_PREFIXES
        ):
            if dry_run:
                print(f"  [SKIP critical] {row['tool_name']} | {pattern[:60]}")
            continue

        approvals = row["cnt"]
        last_seen = row["last_seen"]
        days_since = (datetime.now(timezone.utc).replace(tzinfo=None) - datetime.fromisoformat(last_seen)).total_seconds() / 86400

        existing = conn.execute(
            "SELECT times_seen, last_seen FROM learned_approvals "
            "WHERE tool_name=? AND pattern=?",
            (row["tool_name"], pattern),
        ).fetchone()

        base = 0.5 if not existing else min(0.95, 0.5 + 0.05 * existing["times_seen"])
        confidence = _decay_confidence(base, approvals, days_since)
        active = 1 if approvals >= ACTIVATION_THRESHOLD else 0

        if dry_run:
            status = "ACTIVATE" if active else "pending"
            print(
                f"  [{status}] {row['tool_name']:20} | {pattern[:55]} "
                f"| seen={approvals} conf={confidence}"
            )
            upserted += 1
            continue

        conn.execute(
            """
            INSERT INTO learned_approvals
                (tool_name, pattern, times_seen, last_seen, approved_by, active)
            VALUES (?, ?, ?, ?, 'system', ?)
            ON CONFLICT(tool_name, pattern) DO UPDATE SET
                times_seen  = excluded.times_seen,
                last_seen   = excluded.last_seen,
                active      = excluded.active
            """,
            (row["tool_name"], pattern, approvals, last_seen, active),
        )
        upserted += 1

    if not dry_run:
        conn.commit()
    return upserted


def train_from_plan_approvals(
    conn: sqlite3.Connection,
    lookback_days: int = 30,
    dry_run: bool = False,
) -> int:
    """
    Scan agent_actions for plan_approved events → reinforce related file patterns.
    Returns count of instincts reinforced.
    """
    since = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=lookback_days)).isoformat()

    approved_sessions = conn.execute(
        """
        SELECT DISTINCT session_id FROM agent_actions
        WHERE action_type = 'plan' AND tool_used = 'ExitPlanMode'
          AND success = 1 AND timestamp >= ?
        """,
        (since,),
    ).fetchall()

    reinforced = 0
    for srow in approved_sessions:
        sid = srow["session_id"]
        # Find edit/write actions in the same session (things done after plan approved)
        edits = conn.execute(
            """
            SELECT file_path, COUNT(*) as cnt FROM agent_actions
            WHERE session_id = ? AND action_type IN ('edit', 'write')
              AND success = 1 AND file_path IS NOT NULL
            GROUP BY file_path ORDER BY cnt DESC LIMIT 5
            """,
            (sid,),
        ).fetchall()

        for edit in edits:
            pattern = _normalize_pattern(edit["file_path"])
            if not pattern:
                continue
            if dry_run:
                print(f"  [plan_approved reinforcement] Edit | {pattern[:70]}")
                reinforced += 1
                continue

            existing = conn.execute(
                "SELECT times_applied FROM instincts WHERE keyword=? AND project='jarvis'",
                (pattern,),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE instincts SET times_applied=times_applied+1, "
                    "confidence=MIN(0.95, confidence+0.02), last_applied=? "
                    "WHERE keyword=? AND project='jarvis'",
                    (datetime.now(timezone.utc).replace(tzinfo=None).isoformat(), pattern),
                )
            else:
                conn.execute(
                    "INSERT OR IGNORE INTO instincts "
                    "(keyword, pattern, confidence, times_applied, times_successful, "
                    "source, project, created_at, last_applied) "
                    "VALUES (?, ?, 0.52, 1, 1, 'plan_approved', 'jarvis', ?, ?)",
                    (
                        pattern,
                        f"plan approved → edit {pattern}",
                        datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                        datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                    ),
                )
            reinforced += 1

    if not dry_run:
        conn.commit()
    return reinforced


def apply_confidence_decay(conn: sqlite3.Connection, dry_run: bool = False) -> int:
    """
    Apply time-based confidence decay to all learned_approvals and instincts.
    Returns number of rows updated.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    updated = 0

    # learned_approvals decay
    rows = conn.execute(
        "SELECT id, times_seen, last_seen FROM learned_approvals WHERE active = 1"
    ).fetchall()
    for row in rows:
        try:
            last = datetime.fromisoformat(row["last_seen"])
        except (TypeError, ValueError):
            continue
        days = (now - last).total_seconds() / 86400
        # Recompute from current times_seen
        new_conf = _decay_confidence(0.5, row["times_seen"], days)
        if dry_run:
            print(f"  [decay] learned_approval id={row['id']} conf={new_conf:.4f}")
            updated += 1
            continue
        # Deactivate if decayed below threshold
        new_active = 1 if new_conf >= 0.3 else 0
        conn.execute(
            "UPDATE learned_approvals SET active=? WHERE id=?",
            (new_active, row["id"]),
        )
        updated += 1

    # instincts decay
    inst_rows = conn.execute(
        "SELECT id, confidence, times_applied, last_applied FROM instincts"
    ).fetchall()
    for row in inst_rows:
        try:
            last = datetime.fromisoformat(row["last_applied"])
        except (TypeError, ValueError):
            continue
        days = (now - last).total_seconds() / 86400
        new_conf = _decay_confidence(row["confidence"] or 0.5, row["times_applied"] or 0, days)
        if dry_run:
            updated += 1
            continue
        conn.execute(
            "UPDATE instincts SET confidence=? WHERE id=?",
            (new_conf, row["id"]),
        )
        updated += 1

    if not dry_run:
        conn.commit()
    return updated


def print_summary(conn: sqlite3.Connection) -> None:
    total = conn.execute("SELECT COUNT(*) FROM learned_approvals").fetchone()[0]
    active = conn.execute("SELECT COUNT(*) FROM learned_approvals WHERE active=1").fetchone()[0]
    instinct_count = conn.execute("SELECT COUNT(*) FROM instincts").fetchone()[0]
    print(f"\n  learned_approvals: {active} active / {total} total")
    print(f"  instincts:         {instinct_count} total")


def main() -> None:
    parser = argparse.ArgumentParser(description="Train DQIII8 instincts from session data")
    parser.add_argument("--dry-run", action="store_true", help="Print without writing")
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=30,
        help="How many days of history to analyze (default 30)",
    )
    args = parser.parse_args()

    print(f"\n{'='*55}")
    print(f"train_instincts — {datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"Lookback: {args.lookback_days}d | Dry run: {args.dry_run}")
    print("=" * 55)

    conn = _connect()

    print("\n[1/3] Approval patterns from permission_decisions...")
    n1 = train_from_approvals(conn, lookback_days=args.lookback_days, dry_run=args.dry_run)
    print(f"  → {n1} patterns upserted")

    print("\n[2/3] Reinforcement from plan_approved sessions...")
    n2 = train_from_plan_approvals(conn, lookback_days=args.lookback_days, dry_run=args.dry_run)
    print(f"  → {n2} instincts reinforced")

    print("\n[3/3] Applying confidence decay...")
    n3 = apply_confidence_decay(conn, dry_run=args.dry_run)
    print(f"  → {n3} rows decayed")

    if not args.dry_run:
        print_summary(conn)

    conn.close()
    print(f"\nDone. Total operations: {n1 + n2 + n3}")


if __name__ == "__main__":
    main()
