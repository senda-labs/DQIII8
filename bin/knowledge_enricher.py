#!/usr/bin/env python3
"""
JARVIS — Knowledge Enricher

Enriquece prompts con chunks relevantes del dominio antes de enviarlos al modelo.
Requiere que el dominio haya sido indexado con knowledge_indexer.py --domain.

Uso:
    python3 bin/knowledge_enricher.py --domain social_sciences "calcula VaR"
    python3 bin/knowledge_enricher.py --domain applied_sciences "SOLID principles"
"""

from __future__ import annotations

import json
import math
import os
import struct
import sys
import urllib.error
import urllib.request
from pathlib import Path

JARVIS_ROOT = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
KNOWLEDGE_ROOT = JARVIS_ROOT / "knowledge"
OLLAMA_URL = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"


# ── Embedding helpers ────────────────────────────────────────────────────────


def _embed(text: str) -> list[float] | None:
    """Embed text via Ollama nomic-embed-text. Returns None on failure."""
    payload = json.dumps({"model": EMBED_MODEL, "prompt": text}).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())["embedding"]
    except Exception:
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


# ── Core enrichment function ─────────────────────────────────────────────────


def enrich_with_knowledge(
    prompt: str,
    domain: str,
    max_chunks: int = 3,
    max_tokens: int = 1500,
    min_similarity: float = 0.5,
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
