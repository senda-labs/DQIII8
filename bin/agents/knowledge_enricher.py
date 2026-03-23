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

import json
import os
import sys
from pathlib import Path

JARVIS_ROOT = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
KNOWLEDGE_ROOT = JARVIS_ROOT / "knowledge"

sys.path.insert(0, str(Path(__file__).parent))
from embeddings import get_embedding, cosine_similarity

# Aliases used by existing code
_embed = get_embedding
_cosine = cosine_similarity


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
        # Fallback: keyword match (no embeddings)
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
) -> list[dict]:
    """Returns raw chunks without modifying the prompt.

    Each dict: {"text": str, "score": float, "source": str}
    Returns empty list if index missing or no matches above threshold.
    """
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
    return [
        {
            "text": e.get("text", "").strip(),
            "score": round(sim, 4),
            "source": e.get("source", domain),
        }
        for sim, e in scored[:top_k]
        if e.get("text", "").strip()
    ]


# ── CLI ──────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Enrich a prompt with domain knowledge")
    parser.add_argument("--domain", required=True, help="Domain name (e.g. social_sciences)")
    parser.add_argument("--max-chunks", type=int, default=3, help="Max chunks to inject")
    parser.add_argument("--min-sim", type=float, default=0.5, help="Minimum cosine similarity")
    parser.add_argument("prompt", nargs="?", help="Prompt to enrich (or pass via stdin)")
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
