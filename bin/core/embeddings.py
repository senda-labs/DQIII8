#!/usr/bin/env python3
"""Shared embedding functions for DQIII8.
Uses bge-m3 via Ollama for all vector operations (1024-dim, multilingual)."""

import math
import struct

import requests

OLLAMA_URL = "http://localhost:11434/api/embeddings"
MODEL = "bge-m3"


def get_embedding(text: str, timeout: int = 30) -> list[float] | None:
    """Get embedding vector from bge-m3 via Ollama. Returns None on failure."""
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": MODEL, "prompt": text[:8000]},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()["embedding"]
    except Exception:
        return None


def embedding_to_bytes(embedding: list[float]) -> bytes:
    """Convert embedding list to bytes for SQLite BLOB storage."""
    return struct.pack(f"{len(embedding)}f", *embedding)


def bytes_to_embedding(data: bytes) -> list[float]:
    """Convert bytes from SQLite BLOB back to embedding list."""
    n = len(data) // 4
    return list(struct.unpack(f"{n}f", data))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
