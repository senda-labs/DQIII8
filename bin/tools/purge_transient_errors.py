"""Purge resolved transient errors older than 48 hours.

Usage:
    python3 bin/tools/purge_transient_errors.py [--dry-run]

Designed to run via cron every 24h:
    0 4 * * * cd /root/dqiii8 && python3 bin/tools/purge_transient_errors.py
"""

import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).parent.parent.parent / "database" / "dqiii8.db"
DRY_RUN = "--dry-run" in sys.argv


def purge() -> int:
    """Delete resolved transient errors older than 48 hours. Returns count."""
    if not DB.exists():
        print("[purge] Database not found")
        return 0

    conn = sqlite3.connect(str(DB), timeout=5)
    cursor = conn.execute(
        "SELECT COUNT(*) FROM error_log "
        "WHERE severity = 'transient' AND resolved = 1 "
        "AND timestamp < datetime('now', '-48 hours')"
    )
    count = cursor.fetchone()[0]

    if count == 0:
        print("[purge] No transient errors to purge")
        conn.close()
        return 0

    if DRY_RUN:
        print(f"[purge] Would delete {count} transient errors (dry-run)")
        conn.close()
        return count

    conn.execute(
        "DELETE FROM error_log "
        "WHERE severity = 'transient' AND resolved = 1 "
        "AND timestamp < datetime('now', '-48 hours')"
    )
    conn.commit()
    conn.close()
    print(f"[purge] Deleted {count} resolved transient errors older than 48h")
    return count


if __name__ == "__main__":
    purge()
