#!/usr/bin/env python3
"""One-shot repair: retroactively insert error_log rows for any agent_actions
rows where success=0 has no corresponding error_log entry.

Run on VPS after syncing:
    python3 bin/tools/fix_orphaned_failures.py
    python3 bin/tools/fix_orphaned_failures.py --dry-run
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

try:
    from bin.core.paths import DB_PATH
except ImportError:
    DB_PATH = Path(__file__).resolve().parents[2] / "database" / "dqiii8.db"


FIND_ORPHANS = """
SELECT id, session_id, agent_name, tool_used, error_message, timestamp
FROM agent_actions
WHERE success = 0
  AND id NOT IN (
      SELECT action_id FROM error_log WHERE action_id IS NOT NULL
  )
ORDER BY id
"""

INSERT_RETROACTIVE = """
INSERT INTO error_log
    (timestamp, session_id, agent_name, error_type, error_message,
     keywords, resolved, lesson_added, action_id)
VALUES (?, ?, ?, ?, ?, ?, 1, 0, ?)
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix orphaned success=0 agent_actions rows")
    parser.add_argument("--dry-run", action="store_true", help="Report only, no writes")
    parser.add_argument("--db", default=str(DB_PATH))
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: DB not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        orphans = conn.execute(FIND_ORPHANS).fetchall()
        if not orphans:
            print("No orphaned failures found — nothing to do.")
            return

        print(f"Found {len(orphans)} orphan(s):")
        for row in orphans:
            print(f"  id={row['id']} tool={row['tool_used']} ts={row['timestamp']}")

        if args.dry_run:
            return

        for row in orphans:
            conn.execute(
                INSERT_RETROACTIVE,
                (
                    row["timestamp"],
                    row["session_id"],
                    row["agent_name"] or "unknown",
                    f"{row['tool_used'] or 'unknown'}Error",
                    (row["error_message"] or "Orphaned failure — retroactively logged")[:500],
                    json.dumps(["audit-repair", row["tool_used"] or "unknown"]),
                    row["id"],
                ),
            )

        conn.commit()
        print(f"Inserted {len(orphans)} retroactive error_log row(s). Re-run audit to verify.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
