#!/usr/bin/env python3
"""Delete database/*.db.old files once their ~72h safety-buffer window has
passed (mtime-based). Generic — covers any future *-consolidation-style
retired DB, not just today's dqiii8_metrics.db.old. Cron-safe: logs what it
deletes, never errors on "nothing to do".
"""
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DB_DIR = ROOT / "database"
RETENTION_HOURS = 72


def main():
    now = time.time()
    for f in DB_DIR.glob("*.db.old"):
        age_h = (now - f.stat().st_mtime) / 3600
        if age_h >= RETENTION_HOURS:
            print(f"cleanup_old_backups: removing {f.name} (age {age_h:.1f}h >= {RETENTION_HOURS}h)")
            f.unlink()
        else:
            print(f"cleanup_old_backups: keeping {f.name} (age {age_h:.1f}h < {RETENTION_HOURS}h)")


if __name__ == "__main__":
    main()
