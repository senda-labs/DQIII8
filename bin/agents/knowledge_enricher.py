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
_V4_COSINE_THRESHOLD = 0.70  # for cosine / task_relevance scores
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
    # ── Try hybrid search first ───────────────────────────────────────────────
    pool_k = top_k * 2 if (intent or entity) else top_k
    scored_vs, vs_path = _search_knowledge(prompt, domain, pool_k, min_similarity)
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

        query_vec = _embed(prompt)
        if query_vec is None:
            return []

        scored = []
        for entry in index:
            vec = entry.get("embedding")
            if not vec:
                continue
            sim = _cosine(query_vec, vec)
            if sim >= min_similarity:
                scored.append((sim, entry))

        if not scored:
            return []

        scored.sort(key=lambda x: x[0], reverse=True)

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


def _filter_and_limit(chunks: list[dict], query: str = "") -> list[dict]:
    """Filter chunks by relevance score and limit count.

    Handles two score regimes:
    - task_relevance / cosine: [0, 1] range → threshold _V4_COSINE_THRESHOLD
    - RRF scores: [0.001, 0.02] range → threshold _V4_RRF_THRESHOLD

    Returns empty list if no chunk passes → caller should skip enrichment.
    """
    relevant: list[dict] = []
    for c in chunks:
        # Prefer task_relevance (cosine, normalized) over raw score (may be RRF)
        tr = c.get("task_relevance", 0.0) or 0.0
        raw_score = c.get("score", 0.0) or 0.0

        if tr >= _V4_COSINE_THRESHOLD:
            c["_v4_score"] = tr
            relevant.append(c)
        elif raw_score >= _V4_COSINE_THRESHOLD:
            # Raw score is also in cosine range
            c["_v4_score"] = raw_score
            relevant.append(c)
        elif 0 < raw_score < 0.1 and raw_score >= _V4_RRF_THRESHOLD:
            # RRF range — score is valid but not comparable to cosine
            c["_v4_score"] = raw_score
            relevant.append(c)

    if not relevant:
        log.info(
            "Enricher v4: 0/%d chunks above threshold — skipping enrichment",
            len(chunks),
        )
        return []

    relevant.sort(key=lambda c: c.get("_v4_score", 0), reverse=True)
    top = relevant[:_V4_MAX_CHUNKS]

    log.info(
        "Enricher v4: %d/%d chunks passed (max=%d)",
        len(top),
        len(chunks),
        _V4_MAX_CHUNKS,
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
        filtered = _filter_and_limit(chunks)
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
