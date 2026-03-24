#!/usr/bin/env python3
"""
DQIII8 — Knowledge Search

Semantic search over agent knowledge index using cosine similarity
against nomic-embed-text embeddings.

Usage:
    python3 bin/knowledge_search.py --agent finance-analyst "calcular WACC empresa tech"
    python3 bin/knowledge_search.py --agent python-specialist "rutas Windows FFmpeg" --top-k 3
    python3 bin/knowledge_search.py --agent content-automator "ElevenLabs timeout" --json
"""

import json
import os
import sys
import time
from pathlib import Path

DQIII8_ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
AGENTS_DIR = DQIII8_ROOT / ".claude" / "agents"

sys.path.insert(0, str(Path(__file__).parent))
from embeddings import get_embedding, cosine_similarity

# Approximate tokens = chars / 4
CHARS_PER_TOKEN = 4


def embed_query(text: str) -> list[float]:
    """Embed a query string via Ollama nomic-embed-text."""
    result = get_embedding(text, timeout=30)
    if result is None:
        raise RuntimeError("Ollama nomic-embed-text not available")
    return result


def search(agent_name: str, query: str, top_k: int = 5) -> list[dict]:
    """
    Search agent knowledge for chunks most semantically similar to query.

    Args:
        agent_name: Agent whose index to search (e.g. "finance-analyst").
        query:      Natural language search query.
        top_k:      Maximum number of results to return.

    Returns:
        List of dicts with keys: source, chunk_id, score, text.
        Sorted by score descending.

    Raises:
        FileNotFoundError: If index.json does not exist for the agent.
    """
    index_path = AGENTS_DIR / agent_name / "knowledge" / "index.json"

    if not index_path.exists():
        raise FileNotFoundError(
            f"No index found for agent '{agent_name}'. "
            f"Run: python3 bin/knowledge_indexer.py --agent {agent_name}"
        )

    index: list[dict] = json.loads(index_path.read_text(encoding="utf-8"))
    query_embedding = embed_query(query)

    scored = [
        {
            "source": entry["source"],
            "chunk_id": entry["chunk_id"],
            "score": round(cosine_similarity(query_embedding, entry["embedding"]), 4),
            "text": entry["text"],
        }
        for entry in index
    ]
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Semantic search over DQIII8 agent knowledge")
    parser.add_argument("--agent", required=True, help="Agent name")
    parser.add_argument("query", help="Natural language search query")
    parser.add_argument("--top-k", type=int, default=5, dest="top_k")
    parser.add_argument("--json", action="store_true", dest="json_out", help="Output raw JSON")
    args = parser.parse_args()

    t0 = time.perf_counter()
    try:
        results = search(args.agent, args.query, top_k=args.top_k)
    except FileNotFoundError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    if args.json_out:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    total_chars = sum(len(r["text"]) for r in results)
    approx_tokens = total_chars // CHARS_PER_TOKEN

    print(f'\n[KNOWLEDGE] {args.agent} | "{args.query}"')
    print(f"Time: {elapsed_ms:.0f}ms | Chunks: {len(results)} | ~{approx_tokens} tokens\n")

    for i, r in enumerate(results, 1):
        preview = r["text"][:500]
        suffix = f"  ... [{len(r['text']) - 500} more chars]" if len(r["text"]) > 500 else ""
        print(f"--- [{i}] {r['source']} (score: {r['score']}) ---")
        print(preview)
        if suffix:
            print(suffix)
        print()


if __name__ == "__main__":
    main()
