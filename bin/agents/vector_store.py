#!/usr/bin/env python3
"""
DQIII8 — Vector Store (sqlite-vec)
Manages the vec0 virtual table for KNN embedding search.

Public API:
    init_vec_table()                         → create vec0 + ensure vector_chunks exist
    upsert_vector(chunk_row_id, embedding)   → insert/replace in vec0
    search_vectors(query_embedding, top_k, domain, agent_name) → list[dict]
    migrate_from_json()                      → bulk-load all knowledge index.json files
    search_text(query, top_k, domain)        → convenience: embed query then KNN search

Usage:
    python3 bin/agents/vector_store.py --migrate
    python3 bin/agents/vector_store.py --bench "async patterns"
    python3 bin/agents/vector_store.py --search "Kelly criterion"
"""

import argparse
import json
import os
import sqlite3
import struct
import sys
import time
from pathlib import Path

import sqlite_vec

DQIII8_ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
DB_PATH = DQIII8_ROOT / "database" / "dqiii8.db"
EMBEDDING_DIM = 768  # nomic-embed-text / all-MiniLM-L12 family
VEC_TABLE = "vec_knowledge"


# ── Connection ────────────────────────────────────────────────────────────────


def _conn() -> sqlite3.Connection:
    """Return a connection with sqlite-vec loaded and WAL enabled."""
    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ── Init ──────────────────────────────────────────────────────────────────────


def init_vec_table() -> None:
    """Create the vec0 virtual table if it doesn't exist."""
    with _conn() as conn:
        conn.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS {VEC_TABLE}
            USING vec0(
                chunk_id INTEGER PRIMARY KEY,
                embedding FLOAT[{EMBEDDING_DIM}]
            )
            """)


# ── Serialization ─────────────────────────────────────────────────────────────


def _serialize(embedding: list[float]) -> bytes:
    """Pack a float list into sqlite-vec binary format (little-endian float32)."""
    return struct.pack(f"{len(embedding)}f", *embedding)


# ── Upsert ────────────────────────────────────────────────────────────────────


def upsert_vector(chunk_row_id: int, embedding: list[float]) -> None:
    """Insert or replace a vector in vec0 keyed by vector_chunks.id.
    sqlite-vec 0.1.x does not support INSERT OR REPLACE on vec0, so we
    delete the existing row first (no-op if absent) then insert.
    """
    blob = _serialize(embedding)
    with _conn() as conn:
        # Delete existing vector if present (ignore if not found)
        try:
            conn.execute(f"DELETE FROM {VEC_TABLE} WHERE chunk_id = ?", (chunk_row_id,))
        except sqlite3.OperationalError:
            pass  # table may not exist yet on first call — init_vec_table() handles it
        conn.execute(
            f"INSERT INTO {VEC_TABLE} (chunk_id, embedding) VALUES (?, ?)",
            (chunk_row_id, blob),
        )


# ── Search ────────────────────────────────────────────────────────────────────


def search_vectors(
    query_embedding: list[float],
    top_k: int = 5,
    domain: str | None = None,
    agent_name: str | None = None,
) -> list[dict]:
    """
    KNN search in vec0, then JOIN with vector_chunks for metadata.

    Returns list of dicts with keys: id, source, chunk_id, agent_name,
    domain, text, distance, indexed_at.
    """
    blob = _serialize(query_embedding)

    filter_clauses: list[str] = []
    filter_params: list = []
    if domain:
        filter_clauses.append("vc.domain = ?")
        filter_params.append(domain)
    if agent_name:
        filter_clauses.append("vc.agent_name = ?")
        filter_params.append(agent_name)
    filter_sql = (" AND " + " AND ".join(filter_clauses)) if filter_clauses else ""

    sql = f"""
        SELECT
            vc.id, vc.source, vc.chunk_id, vc.agent_name, vc.domain,
            vc.text, v.distance, vc.indexed_at
        FROM {VEC_TABLE} v
        JOIN vector_chunks vc ON vc.id = v.chunk_id
        WHERE v.embedding MATCH ?
          AND k = ?
          {filter_sql}
        ORDER BY v.distance
    """
    params = [blob, top_k * 3] + filter_params  # over-fetch before domain filter

    with _conn() as conn:
        try:
            rows = conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            # vec0 table may not exist yet
            return []

    # Post-filter by domain/agent (vec0 WHERE only supports MATCH + k)
    results = [dict(r) for r in rows]
    if domain:
        results = [r for r in results if r.get("domain") == domain]
    if agent_name:
        results = [r for r in results if r.get("agent_name") == agent_name]
    return results[:top_k]


# ── Migration ─────────────────────────────────────────────────────────────────


def _find_index_files() -> list[tuple[Path, str, str]]:
    """
    Discover all knowledge index.json files.
    Returns list of (path, agent_name, domain).
    """
    results: list[tuple[Path, str, str]] = []

    # Agent-scoped knowledge: .claude/agents/<agent>/knowledge/index.json
    agents_dir = DQIII8_ROOT / ".claude" / "agents"
    for idx in sorted(agents_dir.glob("*/knowledge/index.json")):
        agent = idx.parent.parent.name
        results.append((idx, agent, ""))

    # Global knowledge: knowledge/<domain>/index.json
    knowledge_dir = DQIII8_ROOT / "knowledge"
    for idx in sorted(knowledge_dir.glob("*/index.json")):
        domain = idx.parent.name
        results.append((idx, "", domain))

    return results


def migrate_from_json(verbose: bool = True) -> dict:
    """
    Load all knowledge index.json files and insert chunks + vectors into DB.
    Skips chunks already present (source + chunk_id + agent_name UNIQUE).

    Returns stats dict.
    """
    init_vec_table()

    files = _find_index_files()
    total_chunks = 0
    new_chunks = 0
    errors = 0
    t0 = time.perf_counter()

    for idx_path, agent_name, domain in files:
        try:
            data = json.loads(idx_path.read_text(encoding="utf-8"))
        except Exception as exc:
            if verbose:
                print(f"  [skip] {idx_path}: {exc}", file=sys.stderr)
            errors += 1
            continue

        if not isinstance(data, list):
            continue

        for item in data:
            total_chunks += 1
            source = item.get("source", "")
            chunk_id = item.get("chunk_id", 0)
            text = item.get("text", "")
            embedding = item.get("embedding")

            if not embedding or len(embedding) != EMBEDDING_DIM:
                continue

            # Upsert metadata row
            with _conn() as conn:
                existing = conn.execute(
                    "SELECT id FROM vector_chunks WHERE source=? AND chunk_id=? AND agent_name=?",
                    (source, chunk_id, agent_name),
                ).fetchone()

                if existing:
                    row_id = existing["id"]
                else:
                    cur = conn.execute(
                        "INSERT INTO vector_chunks "
                        "(source, chunk_id, agent_name, domain, text) VALUES (?,?,?,?,?)",
                        (source, chunk_id, agent_name, domain, text),
                    )
                    row_id = cur.lastrowid
                    new_chunks += 1

            # Upsert vector
            upsert_vector(row_id, embedding)

        if verbose:
            label = agent_name or domain
            print(f"  {label:30s} {len(data):4d} chunks")

    elapsed = time.perf_counter() - t0
    stats = {
        "files": len(files),
        "total_chunks": total_chunks,
        "new_chunks": new_chunks,
        "errors": errors,
        "elapsed_s": round(elapsed, 3),
    }

    if verbose:
        print(f"\n  Migrated: {new_chunks}/{total_chunks} new chunks in {elapsed:.2f}s")

    return stats


# ── Convenience: embed + search ───────────────────────────────────────────────


def _embed_query(text: str) -> list[float] | None:
    """
    Try to embed query text using available model.
    Falls back to None if no embedder is available (caller should use text search).
    """
    # Try sentence-transformers if available
    try:
        from sentence_transformers import SentenceTransformer

        _model_cache = getattr(_embed_query, "_model", None)
        if _model_cache is None:
            _embed_query._model = SentenceTransformer("all-MiniLM-L12-v2")
        emb = _embed_query._model.encode(text, normalize_embeddings=True)
        return emb.tolist()
    except ImportError:
        pass

    # Try ollama nomic-embed-text if available
    try:
        import urllib.request

        payload = json.dumps({"model": "nomic-embed-text", "prompt": text}).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/embeddings",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            return data.get("embedding")
    except Exception:
        pass

    return None


def search_text(
    query: str,
    top_k: int = 5,
    domain: str | None = None,
    agent_name: str | None = None,
) -> list[dict]:
    """Embed query text and run KNN search. Returns same format as search_vectors."""
    emb = _embed_query(query)
    if emb is None:
        print(
            "[vector_store] No embedder available — cannot run KNN search",
            file=sys.stderr,
        )
        return []
    return search_vectors(emb, top_k=top_k, domain=domain, agent_name=agent_name)


# ── Stats ─────────────────────────────────────────────────────────────────────


def stats() -> dict:
    with _conn() as conn:
        chunks = conn.execute("SELECT COUNT(*) FROM vector_chunks").fetchone()[0]
        try:
            vectors = conn.execute(f"SELECT COUNT(*) FROM {VEC_TABLE}").fetchone()[0]
        except sqlite3.OperationalError:
            vectors = 0
        by_domain = conn.execute(
            "SELECT domain, COUNT(*) n FROM vector_chunks GROUP BY domain ORDER BY n DESC"
        ).fetchall()
        by_agent = conn.execute(
            "SELECT agent_name, COUNT(*) n FROM vector_chunks "
            "WHERE agent_name != '' GROUP BY agent_name ORDER BY n DESC"
        ).fetchall()
    return {
        "chunks": chunks,
        "vectors": vectors,
        "by_domain": [dict(r) for r in by_domain],
        "by_agent": [dict(r) for r in by_agent],
    }


# ── CLI ───────────────────────────────────────────────────────────────────────


def _bench(query: str) -> None:
    """Benchmark search latency for a query string."""
    emb = _embed_query(query)
    if emb is None:
        print("[bench] No embedder available")
        return

    # Warm-up
    search_vectors(emb, top_k=5)

    trials = 5
    times = []
    for _ in range(trials):
        t0 = time.perf_counter()
        results = search_vectors(emb, top_k=5)
        times.append(time.perf_counter() - t0)

    avg_ms = sum(times) / len(times) * 1000
    print(f"  Query   : {query!r}")
    print(f"  Avg     : {avg_ms:.1f} ms  (n={trials})")
    print(f"  Results : {len(results)}")
    for r in results[:3]:
        print(f"    [{r['distance']:.4f}] {r['source']} — {r['text'][:80]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DQIII8 vector store")
    parser.add_argument(
        "--migrate", action="store_true", help="Run JSON → DB migration"
    )
    parser.add_argument("--stats", action="store_true", help="Show store stats")
    parser.add_argument("--bench", metavar="QUERY", help="Benchmark search latency")
    parser.add_argument("--search", metavar="QUERY", help="Search knowledge base")
    parser.add_argument("--domain", default=None, help="Filter by domain")
    parser.add_argument("--agent", default=None, help="Filter by agent_name")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    if args.migrate:
        print("── Migrating knowledge index files ─────────────")
        s = migrate_from_json(verbose=True)
        print(f"\n  Files processed : {s['files']}")
        print(f"  Chunks total    : {s['total_chunks']}")
        print(f"  New (inserted)  : {s['new_chunks']}")
        print(f"  Errors          : {s['errors']}")
        print(f"  Time            : {s['elapsed_s']}s")
        print()
        s2 = stats()
        print(f"  DB chunks : {s2['chunks']}  |  vectors : {s2['vectors']}")

    elif args.stats:
        s = stats()
        print(json.dumps(s, indent=2))

    elif args.bench:
        _bench(args.bench)

    elif args.search:
        results = search_text(
            args.search, top_k=args.top_k, domain=args.domain, agent_name=args.agent
        )
        if not results:
            print("No results (embedder unavailable or empty store)")
        for r in results:
            print(f"[{r['distance']:.4f}] {r['source']} — {r['text'][:120]}")

    else:
        parser.print_help()
