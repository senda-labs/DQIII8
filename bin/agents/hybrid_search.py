#!/usr/bin/env python3
"""
DQIII8 — Hybrid Search Engine  (Bloque 9 Fase 2)

Combines three retrieval signals and merges them with Reciprocal Rank Fusion:
  1. Vector (KNN cosine via sqlite-vec)
  2. Keyword (FTS5 over vector_chunks + facts)
  3. Graph (relations table — gracefully empty until Fase 4)

Public API:
    hybrid_search(query, top_k, domain, as_of)   → list[dict]
    search_by_embedding(query_text, top_k, domain) → list[dict]
    search_by_keywords(query_text, top_k, domain)  → list[dict]
    search_by_relations(entities, depth)           → list[dict]
    reciprocal_rank_fusion(result_lists, k)        → list[dict]

Each result dict:
    text, source, domain, score, search_method
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

DQIII8_ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
DB_PATH = DQIII8_ROOT / "database" / "dqiii8.db"

# Weights for RRF per source (higher = more influence when all three present)
_WEIGHT_VECTOR = 1.0
_WEIGHT_KEYWORD = 0.7
_WEIGHT_GRAPH = 0.5


# ── Connection ────────────────────────────────────────────────────────────────


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _vec_conn() -> sqlite3.Connection:
    """Connection with sqlite-vec extension loaded."""
    try:
        import sqlite_vec

        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn
    except Exception as exc:
        raise RuntimeError(f"sqlite-vec unavailable: {exc}") from exc


# ── 1. Vector search ──────────────────────────────────────────────────────────


def search_by_embedding(
    query_text: str,
    top_k: int = 10,
    domain: Optional[str] = None,
) -> list[dict]:
    """
    KNN cosine search via sqlite-vec.
    Returns list of result dicts with search_method='vector'.
    Empty list if embedder or vector table unavailable.
    """
    try:
        import sys

        sys.path.insert(0, str(Path(__file__).parent))
        from vector_store import search_vectors, _embed_query

        emb = _embed_query(query_text)
        if emb is None:
            log.debug("[hybrid] vector: no embedder")
            return []

        raw = search_vectors(emb, top_k=top_k, domain=domain)
        results = []
        for r in raw:
            # cosine distance → similarity: distance=0 → sim=1
            sim = max(0.0, 1.0 - float(r.get("distance", 1.0)))
            results.append(
                {
                    "id": r.get("id"),
                    "item_type": "chunk",
                    "text": r.get("text", ""),
                    "source": r.get("source", ""),
                    "domain": r.get("domain", domain or ""),
                    "score": round(sim, 4),
                    "search_method": "vector",
                }
            )
        log.debug("[hybrid] vector: %d results", len(results))
        return results
    except Exception as exc:
        log.warning("[hybrid] vector search failed: %s", exc)
        return []


# ── 2. Keyword search (FTS5) ──────────────────────────────────────────────────


def search_by_keywords(
    query_text: str,
    top_k: int = 10,
    domain: Optional[str] = None,
) -> list[dict]:
    """
    FTS5 keyword search over chunks_fts (vector_chunks) and facts_fts (facts).
    Results from both tables are merged and deduplicated by text hash.
    Returns list with search_method='keyword'.
    Empty list if FTS5 tables don't exist or query is blank.
    """
    query_text = query_text.strip()
    if not query_text:
        return []

    # Escape FTS5 special characters to avoid query syntax errors
    fts_query = _escape_fts5(query_text)
    results: list[dict] = []

    with _conn() as conn:
        # ── chunks_fts (vector_chunks) ────────────────────────────────────────
        try:
            domain_filter = "AND c.domain = ?" if domain else ""
            params: list = [fts_query]
            if domain:
                params.append(domain)
            params.append(top_k)

            sql = f"""
                SELECT c.id, c.source, c.text, c.domain, c.agent_name,
                       bm25(chunks_fts) AS bm25_score
                FROM chunks_fts
                JOIN vector_chunks c ON c.id = chunks_fts.rowid
                WHERE chunks_fts MATCH ?
                  {domain_filter}
                ORDER BY bm25_score
                LIMIT ?
            """
            rows = conn.execute(sql, params).fetchall()
            for r in rows:
                # bm25() returns negative values in SQLite FTS5 (more negative = better)
                score = max(0.0, min(1.0, 1.0 / (1.0 - float(r["bm25_score"]))))
                results.append(
                    {
                        "id": r["id"],
                        "item_type": "chunk",
                        "text": r["text"],
                        "source": r["source"],
                        "domain": r["domain"] or "",
                        "score": round(score, 4),
                        "search_method": "keyword",
                    }
                )
        except sqlite3.OperationalError as exc:
            log.debug("[hybrid] chunks_fts unavailable: %s", exc)

        # ── facts_fts (temporal facts) ────────────────────────────────────────
        try:
            f_params: list = [fts_query]
            f_domain_filter = "AND f.domain = ?" if domain else ""
            if domain:
                f_params.append(domain)
            f_params.append(top_k)

            fsql = f"""
                SELECT f.id, f.entity, f.predicate, f.value, f.domain,
                       bm25(facts_fts) AS bm25_score
                FROM facts_fts
                JOIN facts f ON f.id = facts_fts.rowid
                WHERE facts_fts MATCH ?
                  AND f.valid_until IS NULL
                  {f_domain_filter}
                ORDER BY bm25_score
                LIMIT ?
            """
            frows = conn.execute(fsql, f_params).fetchall()
            for r in frows:
                score = max(0.0, min(1.0, 1.0 / (1.0 - float(r["bm25_score"]))))
                text = f"{r['entity']} {r['predicate']} {r['value']}"
                results.append(
                    {
                        "id": r["id"],
                        "item_type": "fact",
                        "text": text,
                        "source": f"fact:{r['entity']}:{r['predicate']}",
                        "domain": r["domain"] or "",
                        "score": round(score, 4),
                        "search_method": "keyword",
                    }
                )
        except sqlite3.OperationalError as exc:
            log.debug("[hybrid] facts_fts unavailable: %s", exc)

    log.debug("[hybrid] keyword: %d results", len(results))
    return results


def _escape_fts5(query: str) -> str:
    """Wrap each token in double quotes to avoid FTS5 syntax errors."""
    tokens = [t.strip() for t in query.split() if t.strip()]
    if not tokens:
        return '""'
    # Quote each token so special chars are treated literally
    return " ".join(f'"{t.replace(chr(34), "")}"' for t in tokens)


# ── 3. Graph / relations search ───────────────────────────────────────────────


def search_by_relations(
    entities: list[str],
    depth: int = 1,
) -> list[dict]:
    """
    BFS over the relations table up to `depth` hops from any entity in `entities`.
    Returns list with search_method='graph'.
    Gracefully returns [] if relations table is empty or entities list is empty.
    """
    if not entities:
        return []

    visited_entities: set[str] = set(entities)
    frontier: set[str] = set(entities)
    results: list[dict] = []

    with _conn() as conn:
        try:
            # Quick check — avoid traversal if table is empty
            total = conn.execute(
                "SELECT COUNT(*) FROM relations WHERE valid_until IS NULL"
            ).fetchone()[0]
            if total == 0:
                return []

            for _ in range(depth):
                if not frontier:
                    break
                placeholders = ",".join("?" * len(frontier))
                rows = conn.execute(
                    f"""
                    SELECT subject, predicate, object, domain, confidence
                    FROM relations
                    WHERE valid_until IS NULL
                      AND (subject IN ({placeholders}) OR object IN ({placeholders}))
                    """,
                    list(frontier) * 2,
                ).fetchall()

                next_frontier: set[str] = set()
                for r in rows:
                    text = f"{r['subject']} {r['predicate']} {r['object']}"
                    results.append(
                        {
                            "text": text,
                            "source": f"relation:{r['subject']}:{r['predicate']}",
                            "domain": r["domain"] or "",
                            "score": round(float(r["confidence"]), 4),
                            "search_method": "graph",
                        }
                    )
                    for entity in (r["subject"], r["object"]):
                        if entity not in visited_entities:
                            next_frontier.add(entity)
                            visited_entities.add(entity)

                frontier = next_frontier

        except sqlite3.OperationalError as exc:
            log.debug("[hybrid] relations unavailable: %s", exc)
            return []

    log.debug("[hybrid] graph: %d results depth=%d", len(results), depth)
    return results


# ── 4. Reciprocal Rank Fusion ─────────────────────────────────────────────────


def reciprocal_rank_fusion(
    result_lists: list[tuple[list[dict], float]],
    k: int = 60,
) -> list[dict]:
    """
    Standard RRF merge across multiple ranked lists.

    Args:
        result_lists: list of (results, weight) tuples.
                      weight scales the RRF contribution of each list.
        k:            RRF smoothing constant (default 60).

    Returns:
        List of merged result dicts, sorted by rrf_score descending.
        Each dict retains the original fields plus 'rrf_score'.
    """
    # Map text → accumulated score + best metadata
    scores: dict[str, float] = {}
    meta: dict[str, dict] = {}

    for results, weight in result_lists:
        for rank, item in enumerate(results, start=1):
            key = item.get("text", "")[:200]  # dedup key
            rrf_contrib = weight / (k + rank)
            scores[key] = scores.get(key, 0.0) + rrf_contrib
            if key not in meta:
                meta[key] = dict(item)
            else:
                # Keep the highest individual score seen across sources
                if item.get("score", 0) > meta[key].get("score", 0):
                    meta[key]["score"] = item["score"]
                # Merge search_method label
                existing_method = meta[key].get("search_method", "")
                new_method = item.get("search_method", "")
                if new_method and new_method not in existing_method:
                    meta[key]["search_method"] = f"{existing_method}+{new_method}"

    merged = []
    for key, rrf_score in scores.items():
        entry = dict(meta[key])
        entry["rrf_score"] = round(rrf_score, 6)
        merged.append(entry)

    merged.sort(key=lambda x: x["rrf_score"], reverse=True)
    return merged


# ── 5. hybrid_search ──────────────────────────────────────────────────────────


def hybrid_search(
    query: str,
    top_k: int = 5,
    domain: Optional[str] = None,
    as_of: Optional[str] = None,
) -> tuple[list[dict], str]:
    """
    Orchestrate vector + keyword + graph search and merge with RRF.

    Returns:
        (results[:top_k], method_used)
        method_used is one of: "hybrid", "vector_only", "keyword_only", "empty"

    Rules:
    - Never fails because one source is empty.
    - At least one source must return results; if none do → ([], "empty").
    - method_used reflects which sources contributed.
    """
    # Over-fetch per source so RRF has candidates to work with
    fetch_k = max(top_k * 3, 15)

    vec_results = search_by_embedding(query, top_k=fetch_k, domain=domain)
    kw_results = search_by_keywords(query, top_k=fetch_k, domain=domain)

    # Extract entity terms for graph hop (top words, 2+ chars)
    entity_terms = [w for w in query.split() if len(w) >= 3]
    graph_results = search_by_relations(entity_terms, depth=1)

    # Build the lists that actually have results
    ranked_lists: list[tuple[list[dict], float]] = []
    sources_used: list[str] = []

    if vec_results:
        ranked_lists.append((vec_results, _WEIGHT_VECTOR))
        sources_used.append("vector")
    if kw_results:
        ranked_lists.append((kw_results, _WEIGHT_KEYWORD))
        sources_used.append("keyword")
    if graph_results:
        ranked_lists.append((graph_results, _WEIGHT_GRAPH))
        sources_used.append("graph")

    if not ranked_lists:
        log.debug(
            "[hybrid] no results from any source for query=%r domain=%s", query, domain
        )
        return [], "empty"

    if len(ranked_lists) == 1:
        src = sources_used[0]
        method = f"{src}_only"
        candidates = ranked_lists[0][0][:top_k]
        log.debug("[hybrid] %s: %d results", method, len(candidates))
    else:
        candidates = reciprocal_rank_fusion(ranked_lists, k=60)
        method = "hybrid"
        log.debug(
            "[hybrid] hybrid (%s): %d merged → %d",
            "+".join(sources_used),
            len(candidates),
            min(top_k, len(candidates)),
        )

    # ── Relevance re-ranking (Fase 3) ─────────────────────────────────────────
    candidates = _apply_relevance(candidates[:top_k], query)
    return candidates, method


def _apply_relevance(results: list[dict], query: str) -> list[dict]:
    """
    Post-RRF relevance scoring: final_score = rrf_score * (0.5 + 0.5 * relevance).
    Also logs access for each result via temporal_memory.log_access.
    No-ops gracefully if temporal_memory is unavailable.
    """
    try:
        import sys

        sys.path.insert(0, str(Path(__file__).parent))
        from temporal_memory import compute_relevance, log_access
    except Exception:
        return results  # relevance module unavailable — return as-is

    rescored = []
    for r in results:
        item_id = r.get("id")
        item_type = r.get("item_type", "chunk")
        base = float(r.get("rrf_score", r.get("score", 0.0)))

        if item_id is not None:
            try:
                rel = compute_relevance(item_id, item_type)
                r["relevance"] = round(rel, 4)
                r["final_score"] = round(base * (0.5 + 0.5 * rel), 6)
                log_access(item_id, item_type, query_text=query)
            except Exception:
                r["final_score"] = base
        else:
            r["final_score"] = base

        rescored.append(r)

    rescored.sort(key=lambda x: x["final_score"], reverse=True)
    log.debug("[hybrid] relevance applied to %d results", len(rescored))
    return rescored


# ── CLI ───────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import argparse
    import json

    logging.basicConfig(level=logging.DEBUG, format="%(message)s")

    parser = argparse.ArgumentParser(description="DQIII8 hybrid search")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--domain", default=None)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    results, method = hybrid_search(args.query, top_k=args.top_k, domain=args.domain)
    print(f"method={method}  results={len(results)}")
    for r in results:
        print(
            f"  [{r.get('rrf_score', r.get('score', 0)):.4f}] "
            f"({r['search_method']}) {r['source']} — {r['text'][:80]}"
        )
