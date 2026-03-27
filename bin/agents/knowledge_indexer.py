#!/usr/bin/env python3
"""
DQIII8 — Knowledge Indexer

Chunks agent knowledge documents (.md), generates embeddings via Ollama
bge-m3 (1024-dim, multilingual), and saves to .claude/agents/{agent}/knowledge/index.json.

Usage:
    python3 bin/knowledge_indexer.py --agent finance-analyst
    python3 bin/knowledge_indexer.py --agent content-automator
    python3 bin/knowledge_indexer.py --agent python-specialist
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import requests

DQIII8_ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
AGENTS_DIR = DQIII8_ROOT / ".claude" / "agents"
KNOWLEDGE_ROOT = DQIII8_ROOT / "knowledge"
OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "bge-m3"


def chunk_document(filepath: Path, max_lines: int = 100) -> list[str]:
    """
    Divide a .md file into chunks using ## headers as separators.
    Falls back to max_lines split when no header is found within the limit.
    Returns list of non-empty text chunks.
    """
    text = filepath.read_text(encoding="utf-8")
    lines = text.splitlines()

    chunks: list[str] = []
    current: list[str] = []

    for line in lines:
        # New ## section header → flush current chunk and start fresh
        if re.match(r"^## ", line) and current:
            chunk_text = "\n".join(current).strip()
            if chunk_text:
                chunks.append(chunk_text)
            current = [line]
        else:
            current.append(line)

        # Hard split at max_lines even without a header boundary
        if len(current) >= max_lines:
            chunk_text = "\n".join(current).strip()
            if chunk_text:
                chunks.append(chunk_text)
            current = []

    if current:
        chunk_text = "\n".join(current).strip()
        if chunk_text:
            chunks.append(chunk_text)

    return chunks


def embed_chunk(text: str) -> list[float]:
    """
    Generate a dense embedding vector via Ollama bge-m3.
    Raises requests.HTTPError on failure.
    """
    response = requests.post(
        OLLAMA_EMBED_URL,
        json={"model": EMBED_MODEL, "prompt": text},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["embedding"]


def index_agent_knowledge(agent_name: str) -> None:
    """
    Index all .md files in .claude/agents/{agent_name}/knowledge/.
    Writes embeddings + source text to knowledge/index.json.
    Skips index.json itself if present.
    """
    knowledge_dir = AGENTS_DIR / agent_name / "knowledge"

    if not knowledge_dir.exists():
        print(
            f"[ERROR] Knowledge directory not found: {knowledge_dir}", file=sys.stderr
        )
        sys.exit(1)

    md_files = sorted(f for f in knowledge_dir.glob("*.md"))
    if not md_files:
        print(f"[WARN] No .md files found in {knowledge_dir}")
        return

    print(f"[INDEXER] {agent_name}: {len(md_files)} file(s) to index")

    index: list[dict] = []

    for filepath in md_files:
        print(f"  {filepath.name}")
        chunks = chunk_document(filepath)
        print(f"    {len(chunks)} chunk(s)")

        for i, chunk in enumerate(chunks):
            t0 = time.perf_counter()
            embedding = embed_chunk(chunk)
            elapsed_ms = (time.perf_counter() - t0) * 1000

            index.append(
                {
                    "source": filepath.name,
                    "chunk_id": i,
                    "text": chunk,
                    "embedding": embedding,
                }
            )
            print(f"    chunk {i}: {len(chunk):>4} chars | {elapsed_ms:>5.0f}ms")

    index_path = knowledge_dir / "index.json"
    index_path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    total_kb = index_path.stat().st_size / 1024
    print(
        f"\n[OK] {agent_name}: {len(index)} chunks → {index_path} ({total_kb:.0f} KB)"
    )


def index_domain_knowledge(domain: str) -> None:
    """
    Index all .md files in knowledge/{domain}/**/ (recursive).
    Skips PREMIUM_* files and INDEX.md files.
    Writes embeddings + source text to knowledge/{domain}/index.json.
    """
    domain_dir = KNOWLEDGE_ROOT / domain

    if not domain_dir.exists():
        print(f"[ERROR] Domain directory not found: {domain_dir}", file=sys.stderr)
        sys.exit(1)

    md_files = sorted(
        f
        for f in domain_dir.rglob("*.md")
        if not f.name.startswith("PREMIUM_") and f.name != "INDEX.md"
    )
    if not md_files:
        print(f"[WARN] No indexable .md files found in {domain_dir}")
        return

    print(f"[INDEXER] domain={domain}: {len(md_files)} file(s) to index")

    index: list[dict] = []

    for filepath in md_files:
        rel = filepath.relative_to(domain_dir)
        print(f"  {rel}")
        chunks = chunk_document(filepath)
        print(f"    {len(chunks)} chunk(s)")

        for i, chunk in enumerate(chunks):
            t0 = time.perf_counter()
            embedding = embed_chunk(chunk)
            elapsed_ms = (time.perf_counter() - t0) * 1000

            index.append(
                {
                    "source": str(rel),
                    "chunk_id": i,
                    "text": chunk,
                    "embedding": embedding,
                }
            )
            print(f"    chunk {i}: {len(chunk):>4} chars | {elapsed_ms:>5.0f}ms")

    index_path = domain_dir / "index.json"
    index_path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    total_kb = index_path.stat().st_size / 1024
    print(
        f"\n[OK] domain={domain}: {len(index)} chunks → {index_path} ({total_kb:.0f} KB)"
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Index agent knowledge documents with bge-m3"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--agent", help="Agent name (e.g. finance-analyst)")
    group.add_argument("--domain", help="Knowledge domain (e.g. social_sciences)")
    args = parser.parse_args()

    if args.agent:
        index_agent_knowledge(args.agent)
    else:
        index_domain_knowledge(args.domain)


if __name__ == "__main__":
    main()
