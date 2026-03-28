#!/usr/bin/env python3
"""
reconcile_errors.py — Reconcilia agent_actions con success=0 que no tienen
entrada correspondiente en error_log.

Uso: python3 bin/reconcile_errors.py [--dry-run]
Exit code: 0 si OK, 1 si el reconciliador mismo falla.
"""

import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
from db import get_db, DB_PATH as DB

DRY_RUN = "--dry-run" in sys.argv


def main() -> int:
    if not DB.exists():
        print(f"[reconcile] DB not found: {DB}", file=sys.stderr)
        return 1

    try:
        with get_db(timeout=10) as conn:
            # Find orphaned failures: agent_actions with success=0 and no error_log row
            orphans = conn.execute("""
                SELECT a.id, a.session_id, a.agent_name, a.tool_used, a.error_message,
                       a.timestamp, a.start_time_ms
                FROM agent_actions a
                LEFT JOIN error_log e ON e.action_id = a.id
                WHERE a.success = 0
                  AND e.id IS NULL
                ORDER BY a.id
                """).fetchall()

            if not orphans:
                print("[reconcile] No orphaned failures found — error_log is in sync.")
                return 0

            print(
                f"[reconcile] Found {len(orphans)} orphaned failure(s){' (dry-run)' if DRY_RUN else ''}:"
            )

            reconciled = 0
            for row in orphans:
                action_id = row["id"]
                session_id = row["session_id"] or "unknown"
                agent_name = row["agent_name"] or "unknown"
                tool = row["tool_used"] or "unknown"
                error_msg = (row["error_message"] or f"{tool} failed (no stderr)")[:500]
                ts = row["timestamp"] or datetime.now().isoformat()

                print(
                    f"  action_id={action_id} session={session_id[:8]} tool={tool}: {error_msg[:60]}..."
                )

                if not DRY_RUN:
                    try:
                        conn.execute(
                            "INSERT INTO error_log "
                            "(timestamp, session_id, agent_name, error_type, error_message, "
                            " keywords, resolved, action_id) "
                            "VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
                            (
                                ts,
                                session_id,
                                agent_name,
                                f"{tool}Error",
                                error_msg,
                                json.dumps([agent_name, tool]),
                                action_id,
                            ),
                        )
                        reconciled += 1
                    except Exception as e:
                        print(
                            f"  [reconcile] INSERT failed for action_id={action_id}: {e}",
                            file=sys.stderr,
                        )

            if not DRY_RUN:
                print(f"[reconcile] Reconciled {reconciled}/{len(orphans)} entries.")

        return 0

    except Exception as e:
        print(f"[reconcile] Fatal error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
