#!/usr/bin/env python3
"""
JARVIS — Memory Decay
Applies weekly decay (0.95/week) to vault_memory entries.
Archives entries with decay_score < 0.1 to vault_memory_archive.
Access bumps decay by +0.2 (capped at 1.0).

Usage:
    python3 bin/memory_decay.py           # apply decay
    python3 bin/memory_decay.py --dry-run # show stats without modifying
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

JARVIS_ROOT = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB = JARVIS_ROOT / "database" / "jarvis_metrics.db"

DECAY_RATE = 0.95
ARCHIVE_THRESHOLD = 0.1
ACCESS_BOOST = 0.2


def main() -> None:
    parser = argparse.ArgumentParser(description="JARVIS memory decay")
    parser.add_argument("--dry-run", action="store_true", help="Show stats without modifying")
    args = parser.parse_args()

    if not DB.exists():
        print("[memory_decay] DB not found — skipping")
        sys.exit(0)

    conn = sqlite3.connect(str(DB), timeout=5)

    # Fetch all vault_memory entries with decay info
    rows = conn.execute(
        "SELECT id, subject, predicate, object, decay_score, last_accessed, access_count, "
        "last_seen FROM vault_memory"
    ).fetchall()

    now = datetime.now()
    to_decay = []
    to_archive = []

    for row in rows:
        rid, subject, predicate, obj, decay_score, last_accessed, access_count, last_seen = row
        decay_score = decay_score if decay_score is not None else 1.0
        access_count = access_count or 0

        # Determine weeks since last access (or creation)
        ref_date_str = last_accessed or last_seen or now.isoformat()
        try:
            ref_date = datetime.fromisoformat(ref_date_str)
        except Exception:
            ref_date = now

        weeks_elapsed = max(0.0, (now - ref_date).total_seconds() / 604800)
        new_score = decay_score * (DECAY_RATE**weeks_elapsed)
        new_score = round(max(0.0, new_score), 4)

        if new_score < ARCHIVE_THRESHOLD:
            to_archive.append(
                (rid, subject, predicate, obj, new_score, last_accessed, access_count, last_seen)
            )
        else:
            to_decay.append((new_score, rid))

    print(f"[memory_decay] Total entries: {len(rows)}")
    print(f"[memory_decay] To decay (score update): {len(to_decay)}")
    print(f"[memory_decay] To archive (score < {ARCHIVE_THRESHOLD}): {len(to_archive)}")

    if args.dry_run:
        # Show preview table
        if to_archive:
            print("\n--- Entries to be ARCHIVED ---")
            for row in to_archive[:10]:
                print(f"  [{row[4]:.3f}] {row[1]}.{row[2]}={row[3][:40]}")
        print("\n[memory_decay] Dry run — no changes applied.")
        conn.close()
        sys.exit(0)

    # Apply decay updates
    for new_score, rid in to_decay:
        conn.execute("UPDATE vault_memory SET decay_score=? WHERE id=?", (new_score, rid))

    # Archive entries below threshold
    archived = 0
    for (
        rid,
        subject,
        predicate,
        obj,
        new_score,
        last_accessed,
        access_count,
        last_seen,
    ) in to_archive:
        try:
            conn.execute(
                "INSERT INTO vault_memory_archive "
                "(subject, predicate, object, last_seen, decay_score, last_accessed, access_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (subject, predicate, obj, last_seen, new_score, last_accessed, access_count),
            )
            conn.execute("DELETE FROM vault_memory WHERE id=?", (rid,))
            archived += 1
        except Exception as e:
            print(f"[memory_decay] archive error for id={rid}: {e}")

    conn.commit()
    conn.close()
    print(f"[memory_decay] Done — {len(to_decay)} updated, {archived} archived.")


if __name__ == "__main__":
    main()
