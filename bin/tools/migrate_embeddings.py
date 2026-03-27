#!/usr/bin/env python3
"""DQIII8 — Embedding Migration: nomic-embed-text (768d) → bge-m3 (1024d).

Drops vec_knowledge (768-dim), recreates with 1024-dim, re-embeds all chunks,
and recalculates subdomain centroids.

Usage:
    python3 bin/tools/migrate_embeddings.py
"""

from __future__ import annotations

import json
import sqlite3
import struct
import sys
import time
import urllib.request
from pathlib import Path

DQIII8_ROOT = Path("/root/dqiii8")
DB_PATH = DQIII8_ROOT / "database" / "dqiii8.db"
MODEL = "bge-m3"
EMBEDDING_DIM = 1024
OLLAMA_URL = "http://localhost:11434/api/embeddings"


def _embed(text: str) -> list[float] | None:
    """Get embedding from bge-m3 via Ollama."""
    try:
        payload = json.dumps({"model": MODEL, "prompt": text[:8000]}).encode("utf-8")
        req = urllib.request.Request(
            OLLAMA_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            emb = result.get("embedding")
            if emb and len(emb) == EMBEDDING_DIM:
                return emb
    except Exception as exc:
        print(f"  [embed error] {exc}", file=sys.stderr)
    return None


def _serialize(embedding: list[float]) -> bytes:
    return struct.pack(f"{len(embedding)}f", *embedding)


def _load_sqlite_vec(conn: sqlite3.Connection) -> None:
    """Load sqlite-vec extension."""
    import sqlite_vec

    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)


def main() -> None:
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")

    # ── Step 1: Drop old vec_knowledge (768-dim) ──────────────────────────
    print("[1/4] Dropping old vec_knowledge table...")
    _load_sqlite_vec(conn)
    conn.execute("DROP TABLE IF EXISTS vec_knowledge")
    conn.commit()

    # ── Step 2: Recreate with 1024-dim ────────────────────────────────────
    print(f"[2/4] Creating vec_knowledge with {EMBEDDING_DIM} dims...")
    conn.execute(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS vec_knowledge
        USING vec0(
            chunk_id INTEGER PRIMARY KEY,
            embedding FLOAT[{EMBEDDING_DIM}] distance_metric=cosine
        )
    """)
    conn.commit()

    # ── Step 3: Re-embed all chunks ───────────────────────────────────────
    chunks = conn.execute("SELECT id, text FROM vector_chunks ORDER BY id").fetchall()
    total = len(chunks)
    print(f"[3/4] Re-embedding {total} chunks with {MODEL}...")

    success = 0
    errors = 0
    t0 = time.time()

    for i, (chunk_id, text) in enumerate(chunks):
        emb = _embed(text)
        if emb is None:
            errors += 1
            continue

        blob = _serialize(emb)
        try:
            conn.execute("DELETE FROM vec_knowledge WHERE chunk_id = ?", (chunk_id,))
            conn.execute(
                "INSERT INTO vec_knowledge (chunk_id, embedding) VALUES (?, ?)",
                (chunk_id, blob),
            )
            success += 1
        except Exception as exc:
            errors += 1
            print(f"  [insert error] chunk {chunk_id}: {exc}", file=sys.stderr)

        if (i + 1) % 50 == 0 or i + 1 == total:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (total - i - 1) / rate if rate > 0 else 0
            print(
                f"  {i + 1}/{total} ({success} ok, {errors} err) "
                f"— {rate:.1f} chunks/s, ETA {eta:.0f}s"
            )

        # Commit every 100 chunks
        if (i + 1) % 100 == 0:
            conn.commit()

    conn.commit()
    elapsed = time.time() - t0
    print(f"  Done: {success}/{total} re-embedded in {elapsed:.1f}s ({errors} errors)")

    # ── Step 4: Recalculate subdomain centroids ───────────────────────────
    print("[4/4] Recalculating subdomain centroids...")
    subdomains = conn.execute(
        "SELECT DISTINCT subdomain, domain FROM subdomain_centroids"
    ).fetchall()

    for subdomain, domain in subdomains:
        rows = conn.execute(
            "SELECT vc.id FROM vector_chunks vc "
            "WHERE vc.subdomain = ? AND vc.domain = ?",
            (subdomain, domain),
        ).fetchall()

        if len(rows) < 3:
            continue

        chunk_ids = [r[0] for r in rows]
        embeddings: list[list[float]] = []
        for cid in chunk_ids:
            blob_row = conn.execute(
                "SELECT embedding FROM vec_knowledge WHERE chunk_id = ?", (cid,)
            ).fetchone()
            if blob_row and blob_row[0]:
                n_dims = len(blob_row[0]) // 4
                emb = list(struct.unpack(f"{n_dims}f", blob_row[0]))
                embeddings.append(emb)

        if not embeddings:
            continue

        n_dims = len(embeddings[0])
        centroid = [0.0] * n_dims
        for emb in embeddings:
            for j in range(n_dims):
                centroid[j] += emb[j]
        for j in range(n_dims):
            centroid[j] /= len(embeddings)

        centroid_blob = struct.pack(f"{n_dims}f", *centroid)
        conn.execute(
            "INSERT OR REPLACE INTO subdomain_centroids "
            "(subdomain, domain, centroid, chunk_count, updated_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            (subdomain, domain, centroid_blob, len(embeddings)),
        )
        print(f"  {subdomain}: {len(embeddings)} embeddings → centroid ({n_dims}d)")

    conn.commit()
    conn.close()
    print("\nMigration complete.")


if __name__ == "__main__":
    main()
