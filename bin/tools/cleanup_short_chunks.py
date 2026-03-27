#!/usr/bin/env python3
"""Remove chunks with <100 chars from all tables. Creates backup first."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import sqlite_vec

DB = Path("/root/dqiii8/database/dqiii8.db")
MIN_CHARS = 100


def main() -> None:
    conn = sqlite3.connect(str(DB))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    # Backup
    conn.execute(
        "CREATE TABLE IF NOT EXISTS vector_chunks_cleanup_backup_20260327 "
        "AS SELECT * FROM vector_chunks WHERE length(text) < ?",
        (MIN_CHARS,),
    )
    backup_count = conn.execute(
        "SELECT COUNT(*) FROM vector_chunks_cleanup_backup_20260327"
    ).fetchone()[0]
    print(f"[1/5] Backup: {backup_count} rows")

    # Get IDs + data for FTS delete
    rows = conn.execute(
        "SELECT id, source, text, domain, agent_name FROM vector_chunks WHERE length(text) < ?",
        (MIN_CHARS,),
    ).fetchall()
    print(f"[2/5] Chunks to delete: {len(rows)}")

    if not rows:
        print("Nothing to delete.")
        conn.close()
        return

    # Delete from vec_knowledge
    for rid, *_ in rows:
        conn.execute("DELETE FROM vec_knowledge WHERE chunk_id = ?", (rid,))
    conn.commit()
    print(f"[3/5] vec_knowledge cleaned")

    # Delete from chunks_fts (content-sync FTS5 requires special delete)
    for rid, source, text, domain, agent_name in rows:
        conn.execute(
            "INSERT INTO chunks_fts(chunks_fts, rowid, source, text, domain, agent_name) "
            "VALUES('delete', ?, ?, ?, ?, ?)",
            (rid, source, text, domain or "", agent_name or ""),
        )
    conn.commit()
    print(f"[4/5] chunks_fts cleaned")

    # Delete from vector_chunks
    conn.execute("DELETE FROM vector_chunks WHERE length(text) < ?", (MIN_CHARS,))
    conn.commit()

    remaining = conn.execute("SELECT COUNT(*) FROM vector_chunks").fetchone()[0]
    fts_count = conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0]
    vec_count = conn.execute("SELECT COUNT(*) FROM vec_knowledge").fetchone()[0]

    print(f"[5/5] Deleted {len(rows)} chunks")
    print(f"  vector_chunks: {remaining}")
    print(f"  chunks_fts:    {fts_count}")
    print(f"  vec_knowledge: {vec_count}")
    print(f"  backup:        {backup_count}")

    conn.close()


if __name__ == "__main__":
    main()
