#!/usr/bin/env python3
"""
DQIII8 — Deduplicate vector_chunks

Removes exact duplicate chunks (identical text), keeping the lowest ID.
Syncs vec_knowledge (vec0), chunks_fts (FTS5), and vector_chunks.
Creates a dated backup table before any deletion.

Usage:
    python3 bin/tools/deduplicate_chunks.py --dry-run
    python3 bin/tools/deduplicate_chunks.py --execute
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sqlite3
from collections import defaultdict
from pathlib import Path

import sqlite_vec

DB_PATH = Path("/root/dqiii8/database/dqiii8.db")

log = logging.getLogger(__name__)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def find_duplicates(conn: sqlite3.Connection) -> list[int]:
    """Return list of chunk IDs to delete (duplicates, keeping lowest ID)."""
    rows = conn.execute(
        'SELECT id, text FROM vector_chunks WHERE text IS NOT NULL AND text != ""'
    ).fetchall()

    by_hash: dict[str, list[int]] = defaultdict(list)
    for rid, text in rows:
        h = hashlib.md5(text.encode()).hexdigest()
        by_hash[h].append(rid)

    to_delete: list[int] = []
    for rids in by_hash.values():
        if len(rids) > 1:
            keep = min(rids)
            to_delete.extend(r for r in rids if r != keep)

    return sorted(to_delete)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Deduplicate vector_chunks")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dry-run", action="store_true", help="Show what would be deleted"
    )
    group.add_argument(
        "--execute", action="store_true", help="Actually delete duplicates"
    )
    args = parser.parse_args()

    conn = _connect()

    to_delete = find_duplicates(conn)
    total = conn.execute("SELECT COUNT(*) FROM vector_chunks").fetchone()[0]

    print(f"Total chunks:     {total}")
    print(f"Duplicates found: {len(to_delete)}")
    print(f"After dedup:      {total - len(to_delete)}")

    if not to_delete:
        print("Nothing to deduplicate.")
        conn.close()
        return

    if args.dry_run:
        print("\n--dry-run: no changes made.")
        conn.close()
        return

    # === EXECUTE ===

    # 1. Backup
    print("\n[1/4] Creating backup...")
    conn.execute("DROP TABLE IF EXISTS vector_chunks_backup_20260327")
    conn.execute(
        "CREATE TABLE vector_chunks_backup_20260327 AS SELECT * FROM vector_chunks"
    )
    backup_count = conn.execute(
        "SELECT COUNT(*) FROM vector_chunks_backup_20260327"
    ).fetchone()[0]
    print(f"  Backup: {backup_count} rows")

    # 2. Delete from vec_knowledge (vec0)
    print("[2/4] Deleting from vec_knowledge...")
    for rid in to_delete:
        conn.execute("DELETE FROM vec_knowledge WHERE chunk_id = ?", (rid,))
    conn.commit()

    # 3. Delete from chunks_fts (FTS5 content-sync)
    print("[3/4] Deleting from chunks_fts...")
    for rid in to_delete:
        row = conn.execute(
            "SELECT source, text, domain, agent_name FROM vector_chunks WHERE id = ?",
            (rid,),
        ).fetchone()
        if row:
            conn.execute(
                "INSERT INTO chunks_fts(chunks_fts, rowid, source, text, domain, agent_name) "
                "VALUES('delete', ?, ?, ?, ?, ?)",
                (rid, row[0], row[1], row[2], row[3]),
            )
    conn.commit()

    # 4. Delete from vector_chunks
    print("[4/4] Deleting from vector_chunks...")
    for rid in to_delete:
        conn.execute("DELETE FROM vector_chunks WHERE id = ?", (rid,))
    conn.commit()

    # Verify
    remaining = conn.execute("SELECT COUNT(*) FROM vector_chunks").fetchone()[0]
    fts_count = conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0]
    vec_count = conn.execute("SELECT COUNT(*) FROM vec_knowledge").fetchone()[0]

    print(f"\n=== Results ===")
    print(f"vector_chunks: {remaining}")
    print(f"chunks_fts:    {fts_count}")
    print(f"vec_knowledge: {vec_count}")
    print(f"backup:        {backup_count}")

    conn.close()


if __name__ == "__main__":
    main()
