#!/usr/bin/env python3
"""
DQIII8 — Knowledge Enricher

Enriquece prompts con chunks relevantes del dominio antes de enviarlos al modelo.
Requiere que el dominio haya sido indexado con knowledge_indexer.py --domain.

Uso:
    python3 bin/knowledge_enricher.py --domain social_sciences "calcula VaR"
    python3 bin/knowledge_enricher.py --domain applied_sciences "SOLID principles"
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

import logging

DQIII8_ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
KNOWLEDGE_ROOT = DQIII8_ROOT / "knowledge"

log = logging.getLogger(__name__)

# ── Enricher v4 config ───────────────────────────────────────────────────────
# SIGIR'24 "The Power of Noise": 3-5 docs optimal, "related but not relevant"
# docs are MORE harmful than irrelevant ones.
_ENRICHER_VERSION = os.environ.get("DQ_ENRICHER_VERSION", "v4")

# Thresholds per score type:
# - task_relevance / cosine scores are in [0, 1] range
# - RRF scores are in ~[0.001, 0.02] range — NOT comparable
_V4_COSINE_THRESHOLD = 0.55  # lowered from 0.70: composite reranking handles quality
_V4_RRF_THRESHOLD = 0.005  # for RRF scores (top results ~0.01-0.02)
_V4_MAX_CHUNKS = 5  # SIGIR'24 optimal range: 3-5

sys.path.insert(0, str(Path(__file__).parent))
from embeddings import get_embedding, cosine_similarity

# Aliases used by existing code
_embed = get_embedding
_cosine = cosine_similarity

# ── Hybrid + vector-store integration ────────────────────────────────────────

try:
    from hybrid_search import hybrid_search as _hybrid_search

    _HYBRID_AVAILABLE = True
except Exception:
    _HYBRID_AVAILABLE = False

try:
    from vector_store import search_vectors as _vs_search
    from vector_store import _embed_query as _vs_embed

    _VS_AVAILABLE = True
except Exception:
    _VS_AVAILABLE = False


# ── Query Expansion ES→EN for KNN ───────────────────────────────────────────

_TERM_EXPANSIONS: dict[str, str] = {
    "valoración": "valuation",
    "empresa": "company corporate",
    "financiero": "financial",
    "coste de capital": "cost of capital",
    "flujo de caja": "cash flow",
    "tasa de descuento": "discount rate",
    "rentabilidad": "profitability return",
    "inversión": "investment",
    "deuda": "debt",
    "patrimonio": "equity",
    "balance": "balance sheet",
    "aplicación": "application app",
    "base de datos": "database",
    "servidor": "server",
    "seguridad": "security",
    "rendimiento": "performance",
    "concurrencia": "concurrency",
    "patrón": "pattern",
    "arquitectura": "architecture",
    "despliegue": "deployment",
    "nutrición": "nutrition",
    "dieta": "diet",
    "calorías": "calories",
    "proteínas": "protein intake",
    "macronutrientes": "macronutrients",
    "plan alimenticio": "meal plan",
    "célula": "cell",
    "proteína": "protein",
    "diseñar": "design",
    "construir": "build",
    "analizar": "analyze analysis",
    "optimizar": "optimize optimization",
    "métricas": "metrics KPI",
    "sistema": "system",
}


def _expand_query_for_retrieval(query: str) -> str:
    """Expand Spanish query with English technical terms for better KNN.

    nomic-embed-text maps Spanish/English to partially separate spaces.
    Chunks are mostly English technical. Appends English equivalents.
    Zero LLM calls, deterministic.
    """
    query_lower = query.lower()
    expansions: list[str] = []

    for es_term, en_terms in _TERM_EXPANSIONS.items():
        if es_term in query_lower:
            expansions.append(en_terms)

    if expansions:
        return query + " " + " ".join(expansions)
    return query


def _get_best_subdomains(
    query_embedding: list[float], domain: str, top_n: int = 3
) -> list[str]:
    """Find the top-N subdomains whose centroids are closest to the query.

    Mathematical basis: centroid C_S = mean(embeddings of chunks in subdomain S).
    sim(Q, C_S) estimates how relevant subdomain S is to query Q.

    Returns subdomain names sorted by similarity descending.
    Falls back to [domain] if no centroids available.
    """
    import struct

    db_path = DQIII8_ROOT / "database" / "dqiii8.db"
    try:
        conn = sqlite3.connect(str(db_path), timeout=2)
        rows = conn.execute(
            "SELECT subdomain, centroid, chunk_count FROM subdomain_centroids"
        ).fetchall()
        conn.close()
    except Exception:
        return [domain]

    if not rows:
        return [domain]

    scored: list[tuple[float, str, int]] = []
    for subdomain, centroid_blob, chunk_count in rows:
        if chunk_count < 3:  # Skip tiny subdomains (unstable centroids)
            continue

        n_dims = len(centroid_blob) // 4
        centroid = struct.unpack(f"{n_dims}f", centroid_blob)

        # Cosine similarity
        dot = sum(a * b for a, b in zip(query_embedding, centroid))
        norm_q = sum(a * a for a in query_embedding) ** 0.5
        norm_c = sum(a * a for a in centroid) ** 0.5
        sim = dot / (norm_q * norm_c) if norm_q * norm_c > 0 else 0.0

        scored.append((sim, subdomain, chunk_count))

    scored.sort(reverse=True)

    # The 5 parent domains are also used as subdomain fallbacks for unclassified
    # chunks. When specific subdomains rank highly, exclude parent-domain entries
    # to avoid leaking generic/unclassified chunks (e.g. tenders via social_sciences).
    _parent_domains = {
        "social_sciences",
        "natural_sciences",
        "applied_sciences",
        "formal_sciences",
        "humanities_arts",
    }
    candidates = scored[: top_n + 3]  # over-select to compensate for filtering
    specific = [s for s in candidates if s[1] not in _parent_domains]
    if len(specific) >= top_n:
        best = [s[1] for s in specific[:top_n]]
    elif specific:
        # Pad with parent domains to reach top_n
        best = [s[1] for s in specific]
        for s in candidates:
            if s[1] not in best and len(best) < top_n:
                best.append(s[1])
    else:
        best = [s[1] for s in candidates[:top_n]]

    log.debug(
        "Centroid match: top-%d subdomains = %s (scores: %s)",
        top_n,
        best,
        [f"{s[0]:.3f}" for s in scored[:top_n]],
    )

    return best if best else [domain]


def _search_knowledge(
    prompt: str,
    domain: str,
    top_k: int,
    min_similarity: float,
) -> tuple[list[tuple[float, dict]], str] | tuple[None, None]:
    """
    Unified knowledge search with fallback chain:
      hybrid (vector+keyword+graph) → vector_only → json_fallback (caller handles).
    Returns ([(sim, entry), ...], method) or (None, None) on full failure.
    """
    # ── Hybrid (vector + FTS5 keyword + graph RRF) ────────────────────────────
    if _HYBRID_AVAILABLE:
        try:
            results, method = _hybrid_search(prompt, top_k=top_k * 3, domain=domain)
            if results:
                # RRF scores are in ~[0.001, 0.02] range — not comparable to cosine
                # similarity thresholds. Trust RRF ranking; only drop zero-score rows.
                scored = [
                    (float(r.get("rrf_score", r.get("score", 0.0))), r)
                    for r in results
                    if float(r.get("rrf_score", r.get("score", 0.0))) > 0.0
                ]
                if scored:
                    log.debug(
                        "[enricher] path=%s domain=%s chunks=%d",
                        method,
                        domain,
                        len(scored),
                    )
                    return scored, method
        except Exception as exc:
            log.warning("[enricher] hybrid_search failed, falling back: %s", exc)

    # ── Vector-only fallback ──────────────────────────────────────────────────
    if _VS_AVAILABLE:
        try:
            emb = _vs_embed(prompt)
            if emb is not None:
                raw = _vs_search(emb, top_k=top_k * 3, domain=domain)
                scored = []
                for r in raw:
                    sim = max(0.0, 1.0 - float(r.get("distance", 1.0)))
                    if sim >= min_similarity:
                        scored.append((sim, r))
                if scored:
                    scored.sort(key=lambda x: x[0], reverse=True)
                    log.debug(
                        "[enricher] path=vector_only domain=%s chunks=%d",
                        domain,
                        len(scored),
                    )
                    return scored, "vector_only"
        except Exception as exc:
            log.warning("[enricher] vector_store fallback failed: %s", exc)

    return None, None


# ── Core enrichment function ─────────────────────────────────────────────────


def enrich_with_knowledge(
    prompt: str,
    domain: str,
    max_chunks: int = 3,
    max_tokens: int = 1500,
    min_similarity: float = 0.25,
) -> tuple[str, int]:
    """
    Search relevant chunks from the domain index and prepend them to the prompt.

    Returns: (enriched_prompt, chunks_used)
    If enrichment fails for any reason, returns (original_prompt, 0).
    """
    # ── Try hybrid search first ───────────────────────────────────────────────
    scored_vs, path = _search_knowledge(prompt, domain, max_chunks, min_similarity)
    if scored_vs is not None:
        top = scored_vs[:max_chunks]

        context_parts = []
        total_chars = 0
        max_chars = max_tokens * 4

        for _, entry in top:
            text = entry.get("text", "").strip()
            if not text:
                continue
            remaining = max_chars - total_chars
            if remaining <= 0:
                break
            if len(text) > remaining:
                text = text[:remaining]
            context_parts.append(text)
            total_chars += len(text)

        if context_parts:
            context_block = "\n\n---\n\n".join(context_parts)
            enriched = (
                f"[DOMAIN CONTEXT — {domain.replace('_', ' ').title()}]\n\n"
                f"{context_block}\n\n"
                f"---\n\n"
                f"[USER PROMPT]\n\n{prompt}"
            )
            return enriched, len(top)

    # ── Fallback: JSON cosine ─────────────────────────────────────────────────
    log.debug("[enricher] path=json_fallback domain=%s", domain)
    index_path = KNOWLEDGE_ROOT / domain / "index.json"
    if not index_path.exists():
        return prompt, 0

    try:
        index: list[dict] = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return prompt, 0

    if not index:
        return prompt, 0

    query_vec = _embed(prompt)
    if query_vec is None:
        return prompt, 0

    # Score each chunk
    scored = []
    for entry in index:
        vec = entry.get("embedding")
        if not vec:
            continue
        sim = _cosine(query_vec, vec)
        if sim >= min_similarity:
            scored.append((sim, entry))

    if not scored:
        return prompt, 0

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:max_chunks]

    # Build context block
    context_parts = []
    total_chars = 0
    max_chars = max_tokens * 4  # rough char estimate

    for _, entry in top:
        text = entry.get("text", "").strip()
        if not text:
            continue
        remaining = max_chars - total_chars
        if remaining <= 0:
            break
        if len(text) > remaining:
            text = text[:remaining]
        context_parts.append(text)
        total_chars += len(text)

    if not context_parts:
        return prompt, 0

    context_block = "\n\n---\n\n".join(context_parts)
    enriched = (
        f"[DOMAIN CONTEXT — {domain.replace('_', ' ').title()}]\n\n"
        f"{context_block}\n\n"
        f"---\n\n"
        f"[USER PROMPT]\n\n{prompt}"
    )
    return enriched, len(top)


def get_relevant_chunks(
    prompt: str,
    domain: str,
    top_k: int = 3,
    min_similarity: float = 0.25,
    intent: str = None,
    entity: str = None,
) -> list[dict]:
    """Returns raw chunks without modifying the prompt.

    Each dict: {"text": str, "score": float, "source": str, "task_relevance": float}

    When intent+entity are provided, a second cosine pass re-ranks candidates by
    how well each chunk matches the task's specific action+entity — not just the
    broad topic. Uses stored index embeddings (no extra Ollama calls per chunk).
    Overhead: 1 embedding of task_query (~290ms) over the broader retrieval pool.

    Returns empty list if index missing or no matches above threshold.
    """
    # ── Query expansion ES→EN for better KNN matching ──────────────────────
    search_prompt = _expand_query_for_retrieval(prompt)

    # ── Centroid pre-filter: find best subdomains for this query ────────────
    query_emb = _embed(search_prompt)
    if query_emb is not None:
        best_subdomains = _get_best_subdomains(query_emb, domain, top_n=3)
    else:
        best_subdomains = [domain]

    # ── Try hybrid search first (over-fetch for post-filter) ──────────────
    pool_k = top_k * 3  # over-fetch: centroid filter + task rerank need candidates
    scored_vs, vs_path = _search_knowledge(
        search_prompt, domain, pool_k, min_similarity
    )
    if scored_vs is not None:
        scored = scored_vs
    else:
        # ── Fallback: JSON cosine ─────────────────────────────────────────────
        log.debug("[enricher] path=json_fallback domain=%s", domain)
        index_path = KNOWLEDGE_ROOT / domain / "index.json"
        if not index_path.exists():
            return []

        try:
            index: list[dict] = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            return []

        if not index:
            return []

        if query_emb is None:
            return []

        scored = []
        for entry in index:
            vec = entry.get("embedding")
            if not vec:
                continue
            sim = _cosine(query_emb, vec)
            if sim >= min_similarity:
                scored.append((sim, entry))

        if not scored:
            return []

        scored.sort(key=lambda x: x[0], reverse=True)

    # ── Centroid post-filter: keep chunks from best subdomains ─────────────
    _sources = [e.get("source", "") for _, e in scored]
    _sub_map: dict[str, str] = {}
    if _sources:
        try:
            _db = DQIII8_ROOT / "database" / "dqiii8.db"
            _sconn = sqlite3.connect(str(_db), timeout=2)
            _placeholders = ",".join("?" * len(_sources))
            _srows = _sconn.execute(
                f"SELECT source, subdomain FROM vector_chunks "
                f"WHERE source IN ({_placeholders}) AND subdomain != ''",
                _sources,
            ).fetchall()
            _sconn.close()
            _sub_map = {r[0]: r[1] for r in _srows}
        except Exception:
            pass

    if _sub_map and best_subdomains != [domain]:
        filtered_scored = [
            (sim, e)
            for sim, e in scored
            if _sub_map.get(e.get("source", ""), "") in best_subdomains
        ]
        if filtered_scored:
            log.debug(
                "Centroid filter: %d -> %d chunks (subdomains=%s)",
                len(scored),
                len(filtered_scored),
                best_subdomains,
            )
            scored = filtered_scored
        else:
            log.debug(
                "Centroid filter: no chunks matched subdomains %s, keeping all %d",
                best_subdomains,
                len(scored),
            )

    # ── Task-relevance re-ranking ─────────────────────────────────────────────
    # When intent+entity are provided, re-rank the broader candidate pool by
    # how well each chunk matches the specific task (not just the topic).
    # Uses stored embeddings from the index — no extra per-chunk Ollama calls.
    task_relevance_map: dict[int, float] = {}
    if (intent or entity) and len(scored) > 1:
        task_query = f"{intent or ''} {entity or ''}".strip()
        task_vec = _embed(task_query)
        if task_vec is not None:
            # Retrieve broader pool: up to top_k * 2 candidates to re-rank from
            pool = scored[: top_k * 2]
            reranked = []
            for sim, entry in pool:
                stored_vec = entry.get("embedding")
                task_rel = _cosine(task_vec, stored_vec) if stored_vec else sim
                task_relevance_map[id(entry)] = task_rel
                reranked.append((task_rel, entry))
            reranked.sort(key=lambda x: x[0], reverse=True)
            scored = reranked  # replace ordering with task-relevance ranking

    top_chunks = [
        {
            "text": e.get("text", "").strip(),
            "score": round(sim, 4),
            "source": e.get("source", domain),
            "domain": e.get("domain", domain),
            "subdomain": _sub_map.get(e.get("source", ""), ""),
            "task_relevance": round(task_relevance_map.get(id(e), sim), 4),
        }
        for sim, e in scored[:top_k]
        if e.get("text", "").strip()
        and e.get("source", "").split("/")[-1] not in ("IDENTITY.md", "README.md")
    ]
    _log_chunk_usage(top_chunks, domain)
    return top_chunks


def _log_chunk_usage(chunks: list[dict], domain: str) -> None:
    """Log returned chunks to knowledge_usage for quality tracking."""
    if not chunks:
        return
    db_path = DQIII8_ROOT / "database" / "jarvis_metrics.db"
    if not db_path.exists():
        return
    try:
        conn = sqlite3.connect(str(db_path), timeout=2)
        for chunk in chunks:
            text_hash = hashlib.md5(chunk["text"][:100].encode()).hexdigest()[:16]
            conn.execute(
                "INSERT INTO knowledge_usage "
                "(chunk_source, chunk_text_hash, domain, relevance_score) "
                "VALUES (?, ?, ?, ?)",
                (
                    chunk.get("source", "unknown"),
                    text_hash,
                    domain,
                    chunk.get("score", 0.0),
                ),
            )
        conn.commit()
        conn.close()
    except Exception:
        pass  # fail-open, never block enrichment


# ── Enricher v4: Relevance Filter (SIGIR'24 "Power of Noise") ────────────────


_DEMOTE_PENALTY = 0.70  # 30% score reduction for "demote" verdict
_V4_COMPOSITE_THRESHOLD = (
    0.40  # Composite score threshold (cosine×0.60 + subdomain×0.25 + keyword×0.15)
)


def _classify_query_subdomain(query: str, domain: str) -> str:
    """Classify query into subdomain using keyword matching (zero latency)."""
    try:
        from subdomain_classifier import classify_subdomain

        return classify_subdomain(query, domain)
    except Exception:
        return domain


def _composite_rerank(
    chunks: list[dict], query: str, query_subdomain: str
) -> list[dict]:
    """Rerank chunks using composite score: cosine × 0.60 + subdomain × 0.25 + keyword × 0.15.

    Transforms tiny cosine separations (0.03 between WACC and LCSP) into
    actionable separations (0.35+) by weighting subdomain match and keyword overlap.
    """
    # Extract meaningful query terms (4+ chars, no stopwords)
    _stopwords = {
        "como",
        "para",
        "quiero",
        "hacer",
        "puedo",
        "ayuda",
        "necesito",
        "diseñar",
        "construir",
        "implementar",
        "explicar",
        "calcular",
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "how",
        "what",
        "explain",
        "describe",
        "show",
        "give",
        "help",
    }
    query_terms = set(w.lower() for w in re.findall(r"\b\w{4,}\b", query)) - _stopwords

    for c in chunks:
        base = c.get("_v4_score", c.get("score", 0))

        # Subdomain match: 1.0 exact, 0.3 same parent domain, 0.0 different
        chunk_sub = c.get("subdomain", "")
        if chunk_sub and chunk_sub == query_subdomain:
            sub_score = 1.0
        elif chunk_sub and chunk_sub == c.get("domain", ""):
            # Chunk fell back to parent domain — weak match
            sub_score = 0.3
        else:
            sub_score = 0.0

        # Keyword overlap
        if query_terms:
            chunk_lower = (c.get("text", "") or "")[:1000].lower()
            matches = sum(1 for t in query_terms if t in chunk_lower)
            kw_score = matches / len(query_terms)
        else:
            kw_score = 0.0

        c["_composite"] = round(base * 0.60 + sub_score * 0.25 + kw_score * 0.15, 4)
        c["_subdomain_match"] = sub_score

    chunks.sort(key=lambda c: c.get("_composite", 0), reverse=True)
    return chunks


def _load_health_verdicts() -> dict[str, dict]:
    """Load {chunk_hash → {verdict, redundancy}} from chunk_health JOIN vector_chunks.

    Returns empty dict if chunk_health has no data (fail-open).
    Uses SHA256(text[:200]) as key — same as _chunk_hash().
    """
    db_path = DQIII8_ROOT / "database" / "dqiii8.db"
    if not db_path.exists():
        return {}
    try:
        conn = sqlite3.connect(str(db_path), timeout=2)
        rows = conn.execute(
            "SELECT vc.text, ch.verdict, ch.redundancy_score "
            "FROM chunk_health ch JOIN vector_chunks vc ON vc.id = ch.chunk_id"
        ).fetchall()
        conn.close()
        result: dict[str, dict] = {}
        for text, verdict, redundancy in rows:
            h = hashlib.sha256(text[:200].encode("utf-8")).hexdigest()
            result[h] = {"verdict": verdict, "redundancy": redundancy or 0.5}
        return result
    except Exception:
        return {}


def _filter_and_limit(chunks: list[dict], query: str = "") -> list[dict]:
    """Filter chunks by relevance score, health verdict, and limit count.

    Handles two score regimes:
    - task_relevance / cosine: [0, 1] range → threshold _V4_COSINE_THRESHOLD
    - RRF scores: [0.001, 0.02] range → threshold _V4_RRF_THRESHOLD

    Health verdicts (from chunk_health):
    - "archive" → excluded entirely
    - "demote" → score penalized 30% before threshold check
    - "keep" / unknown → no penalty

    Returns empty list if no chunk passes → caller should skip enrichment.
    """
    health_map = _load_health_verdicts()
    archived = 0

    relevant: list[dict] = []
    for c in chunks:
        # ── Health verdict check ─────────────────────────────────────────
        text = c.get("text", "")
        ch = hashlib.sha256(text[:200].encode("utf-8")).hexdigest() if text else ""
        health = health_map.get(ch, {})
        verdict = health.get("verdict", "keep") if isinstance(health, dict) else health

        if verdict == "archive":
            archived += 1
            continue

        # Prefer task_relevance (cosine, normalized) over raw score (may be RRF)
        tr = c.get("task_relevance", 0.0) or 0.0
        raw_score = c.get("score", 0.0) or 0.0

        # ── Demote penalty: reduce score before threshold check ──────────
        if verdict == "demote":
            tr *= _DEMOTE_PENALTY
            raw_score *= _DEMOTE_PENALTY

        if tr >= _V4_COSINE_THRESHOLD:
            c["_v4_score"] = tr
            c["_v4_verdict"] = verdict
            relevant.append(c)
        elif raw_score >= _V4_COSINE_THRESHOLD:
            c["_v4_score"] = raw_score
            c["_v4_verdict"] = verdict
            relevant.append(c)
        elif 0 < raw_score < 0.1 and raw_score >= _V4_RRF_THRESHOLD:
            c["_v4_score"] = raw_score
            c["_v4_verdict"] = verdict
            relevant.append(c)

    if not relevant:
        log.info(
            "Enricher v4: 0/%d chunks above threshold (archived=%d) — skipping",
            len(chunks),
            archived,
        )
        return []

    # ── Composite reranking (subdomain + keyword) ─────────────────────
    query_subdomain = (
        _classify_query_subdomain(query, relevant[0].get("domain", "")) if query else ""
    )
    if query and query_subdomain:
        relevant = _composite_rerank(relevant, query, query_subdomain)
        # Only apply composite threshold for cosine-range scores.
        # RRF scores (~0.01) produce low composites even for perfect matches.
        is_rrf = all(c.get("_v4_score", 0) < 0.1 for c in relevant)
        if not is_rrf:
            relevant = [
                c for c in relevant if c.get("_composite", 0) >= _V4_COMPOSITE_THRESHOLD
            ]
            if not relevant:
                log.info(
                    "Enricher v4: 0 chunks above composite threshold %.2f — skipping",
                    _V4_COMPOSITE_THRESHOLD,
                )
                return []
    else:
        relevant.sort(key=lambda c: c.get("_v4_score", 0), reverse=True)

    top = relevant[:_V4_MAX_CHUNKS]

    # ── Adaptive Retrieval Gate ──────────────────────────────────────────
    # If ALL passing chunks are demoted, everything we have is redundant
    if all(c.get("_v4_verdict") == "demote" for c in top):
        log.info(
            "Adaptive gate: all %d passing chunks are demoted — skipping",
            len(top),
        )
        return []

    # If no harvested chunks and high average redundancy, LLM already knows this
    _harvested_prefixes = (
        "arxiv:",
        "openalex:",
        "user:",
        "pubmed:",
        "s2:",
        "hackernews:",
    )
    has_harvested = any(
        any((c.get("source") or "").startswith(p) for p in _harvested_prefixes)
        for c in top
    )
    if not has_harvested and health_map:
        redundancies = []
        for c in top:
            text = c.get("text", "")
            ch = hashlib.sha256(text[:200].encode("utf-8")).hexdigest() if text else ""
            h = health_map.get(ch, {})
            r = h.get("redundancy", 0.5) if isinstance(h, dict) else 0.5
            redundancies.append(r)
        avg_r = sum(redundancies) / max(len(redundancies), 1)
        if avg_r > 0.60:
            log.info(
                "Adaptive gate: all legacy, avg_redundancy=%.2f > 0.60 — skipping",
                avg_r,
            )
            return []

    log.info(
        "Enricher v4: %d/%d chunks passed (max=%d, archived=%d, harvested=%s)",
        len(top),
        len(chunks),
        _V4_MAX_CHUNKS,
        archived,
        has_harvested,
    )
    return top


def _compress_to_key_facts(chunks: list[dict]) -> str:
    """Replace full chunk text with cached key_facts for minimal token usage.

    Uses chunk_key_facts via SHA256(text[:200]) — same key as key_facts_generator.
    Fallback: first 150 chars of chunk text.
    """
    hashes = [_chunk_hash(c.get("text", "")) for c in chunks]
    facts_map = _load_cached_facts(hashes)

    items: list[dict] = []
    for c, h in zip(chunks, hashes):
        facts = facts_map.get(h)
        if facts:
            fact_text = "; ".join(facts)
        else:
            fact_text = (c.get("text", "") or "")[:150]
        items.append(
            {
                "d": (c.get("source", "") or c.get("domain", ""))[:30],
                "f": fact_text,
                "s": round(c.get("_v4_score", c.get("score", 0)), 3),
            }
        )

    return json.dumps(items, ensure_ascii=False, separators=(",", ":"))


# ── Structured context builder (Enricher v3) ─────────────────────────────────


def _chunk_hash(text: str) -> str:
    """SHA256 of first 200 chars — matches key_facts_generator cache key."""
    import hashlib

    return hashlib.sha256(text[:200].encode("utf-8")).hexdigest()


def _load_cached_facts(hashes: list[str]) -> dict[str, list[str]]:
    """Return {chunk_hash: [fact, ...]} for hashes present in chunk_key_facts."""
    if not hashes:
        return {}
    db_path = DQIII8_ROOT / "database" / "dqiii8.db"
    if not db_path.exists():
        return {}
    try:
        import json as _json

        conn = sqlite3.connect(str(db_path), timeout=2)
        placeholders = ",".join("?" * len(hashes))
        rows = conn.execute(
            f"SELECT chunk_hash, key_facts FROM chunk_key_facts WHERE chunk_hash IN ({placeholders})",
            hashes,
        ).fetchall()
        conn.close()
        return {row[0]: _json.loads(row[1]) for row in rows}
    except Exception:
        return {}


def build_structured_context(
    chunks: list[dict],
    model_tier: str,
    domain: str,
    max_chars: int = 1200,
    query: str = "",
) -> tuple[str, str]:
    """Build a model-adaptive context block from retrieved knowledge chunks.

    Args:
        chunks:     Output of get_relevant_chunks() — list of {text, score, source, ...}
        model_tier: "small" (ollama) | "medium" (groq/github) | "large" (anthropic)
        domain:     Knowledge domain label for the header
        max_chars:  Hard cap on total context characters

    Returns:
        (context_block, method) where method is one of:
          "toon"            — Token-Optimized Object Notation (small models)
          "json_simple"     — Flat JSON facts array (medium models)
          "json_full"       — Rich JSON with facts + excerpt (large models)
          "text_fallback"   — Plain text excerpt when no cached facts available
    """
    if not chunks:
        return "", "empty"

    # ── Enricher v4: filter + compress before tier-specific formatting ────────
    if _ENRICHER_VERSION == "v4":
        _effective_query = query or (chunks[0].get("text", "")[:200] if chunks else "")
        filtered = _filter_and_limit(chunks, query=_effective_query)
        if not filtered:
            return "", "v4_filtered_all"
        compressed = _compress_to_key_facts(filtered)
        domain_label = domain.replace("_", " ").title()
        block = f"CONTEXT [{domain_label}]:\n{compressed}\n"
        return block, "v4_compressed"

    # ── Enricher v3: original tier-adaptive logic (unchanged) ─────────────────
    import json as _json

    # Resolve cached key facts for all chunks
    hashes = [_chunk_hash(c["text"]) for c in chunks]
    facts_map = _load_cached_facts(hashes)

    domain_label = domain.replace("_", " ").title()

    # ── small (ollama) — TOON ─────────────────────────────────────────────────
    if model_tier == "small":
        lines: list[str] = []
        chars_used = 0
        for c, h in zip(chunks, hashes):
            facts = facts_map.get(h)
            if facts:
                for f in facts:
                    line = f"- {f}"
                    if chars_used + len(line) > max_chars:
                        break
                    lines.append(line)
                    chars_used += len(line) + 1
            else:
                # Fallback: excerpt
                excerpt = c["text"][:120].strip()
                line = f"- {excerpt}"
                if chars_used + len(line) > max_chars:
                    break
                lines.append(line)
                chars_used += len(line) + 1
        if not lines:
            return "", "empty"
        block = f"CONTEXT [{domain_label}]:\n" + "\n".join(lines) + "\n"
        return block, "toon"

    # ── medium (groq / github) — flat JSON facts ──────────────────────────────
    if model_tier == "medium":
        all_facts: list[str] = []
        for c, h in zip(chunks, hashes):
            facts = facts_map.get(h)
            if facts:
                all_facts.extend(facts)
            else:
                all_facts.append(c["text"][:100].strip())
        payload = {"domain": domain_label, "facts": all_facts}
        block = _json.dumps(payload, ensure_ascii=False)
        if len(block) > max_chars:
            # Truncate facts list until it fits
            while len(block) > max_chars and payload["facts"]:
                payload["facts"].pop()
            block = _json.dumps(payload, ensure_ascii=False)
        if not payload["facts"]:
            return "", "empty"
        return block, "json_simple"

    # ── large (anthropic) — rich JSON with facts + excerpt ────────────────────
    chunk_entries = []
    chars_used = 0
    for c, h in zip(chunks, hashes):
        facts = facts_map.get(h)
        excerpt = c["text"][:200].strip()
        entry: dict = {
            "source": c.get("source", ""),
            "score": round(c.get("score", 0.0), 3),
        }
        if facts:
            entry["facts"] = facts
        else:
            entry["excerpt"] = excerpt
        chunk_entries.append(entry)
        chars_used += len(_json.dumps(entry))
        if chars_used > max_chars:
            break

    if not chunk_entries:
        return "", "empty"

    payload = {"domain": domain_label, "chunks": chunk_entries}
    block = _json.dumps(payload, ensure_ascii=False, indent=None)
    if len(block) > max_chars:
        # Drop trailing chunks until fits
        while len(block) > max_chars and payload["chunks"]:
            payload["chunks"].pop()
        block = _json.dumps(payload, ensure_ascii=False, indent=None)

    if not payload["chunks"]:
        return "", "empty"

    return block, "json_full"


# ── CLI ──────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Enrich a prompt with domain knowledge"
    )
    parser.add_argument(
        "--domain", required=True, help="Domain name (e.g. social_sciences)"
    )
    parser.add_argument(
        "--max-chunks", type=int, default=3, help="Max chunks to inject"
    )
    parser.add_argument(
        "--min-sim", type=float, default=0.5, help="Minimum cosine similarity"
    )
    parser.add_argument(
        "prompt", nargs="?", help="Prompt to enrich (or pass via stdin)"
    )
    args = parser.parse_args()

    raw = args.prompt or sys.stdin.read().strip()
    if not raw:
        parser.print_help()
        sys.exit(1)

    result, chunks = enrich_with_knowledge(
        raw, args.domain, args.max_chunks, min_similarity=args.min_sim
    )
    print(f"[enricher] chunks_used={chunks}", file=sys.stderr)
    print(result)
