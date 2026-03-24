#!/usr/bin/env python3
"""
DQIII8 — Memory Decay
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

DQIII8_ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
DB = DQIII8_ROOT / "database" / "dqiii8.db"

DECAY_RATE = 0.95
ARCHIVE_THRESHOLD = 0.1
ACCESS_BOOST = 0.2


def main() -> None:
    parser = argparse.ArgumentParser(description="DQIII8 memory decay")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show stats without modifying"
    )
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
        (
            rid,
            subject,
            predicate,
            obj,
            decay_score,
            last_accessed,
            access_count,
            last_seen,
        ) = row
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
                (
                    rid,
                    subject,
                    predicate,
                    obj,
                    new_score,
                    last_accessed,
                    access_count,
                    last_seen,
                )
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
        _apply_instinct_evolution(DB, dry_run=True)
        sys.exit(0)

    # Apply decay updates
    for new_score, rid in to_decay:
        conn.execute(
            "UPDATE vault_memory SET decay_score=? WHERE id=?", (new_score, rid)
        )

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
                (
                    subject,
                    predicate,
                    obj,
                    last_seen,
                    new_score,
                    last_accessed,
                    access_count,
                ),
            )
            conn.execute("DELETE FROM vault_memory WHERE id=?", (rid,))
            archived += 1
        except Exception as e:
            print(f"[memory_decay] archive error for id={rid}: {e}")

    conn.commit()
    conn.close()
    print(f"[memory_decay] Done — {len(to_decay)} updated, {archived} archived.")

    # Apply instinct evolution (decay unused, promote proven)
    _apply_instinct_evolution(DB, args.dry_run)


def _apply_instinct_evolution(db_path: Path, dry_run: bool) -> None:
    """
    Instinct reinforcement learning:
      - Decay: instincts unused for 30+ days lose 0.02 confidence/cycle (floor 0.1)
      - Promotion: instincts with times_successful > 10 AND success_rate > 0.8
        gain 0.05 confidence/cycle (cap 1.0)

    Instincts are never deleted — they can recover if used again.
    The fast-path threshold in director.py is confidence > 0.7.
    """
    if not db_path.exists():
        return

    conn = sqlite3.connect(str(db_path), timeout=5)
    now = datetime.now()
    cutoff = (now - timedelta(days=30)).isoformat()

    # Fetch all instincts
    rows = conn.execute(
        "SELECT id, keyword, confidence, times_applied, times_successful, last_applied "
        "FROM instincts"
    ).fetchall()

    decayed = promoted = 0
    for rid, keyword, confidence, applied, successful, last_applied in rows:
        confidence = confidence or 0.5
        applied = applied or 0
        successful = successful or 0
        new_conf = confidence

        # Decay: not applied in last 30 days
        if applied == 0 or (last_applied and last_applied < cutoff):
            new_conf = max(0.1, confidence - 0.02)
            if new_conf != confidence:
                decayed += 1

        # Promotion: proven track record
        success_rate = successful / applied if applied > 0 else 0.0
        if successful > 10 and success_rate > 0.8:
            new_conf = min(1.0, new_conf + 0.05)
            if new_conf != confidence:
                promoted += 1

        if new_conf != confidence and not dry_run:
            conn.execute(
                "UPDATE instincts SET confidence=? WHERE id=?",
                (round(new_conf, 4), rid),
            )

    if not dry_run:
        conn.commit()

    conn.close()
    prefix = "[memory_decay dry-run]" if dry_run else "[memory_decay]"
    print(
        f"{prefix} Instincts: {decayed} decayed, {promoted} promoted "
        f"(of {len(rows)} total)"
    )


if __name__ == "__main__":
    main()
