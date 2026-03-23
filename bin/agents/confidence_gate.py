#!/usr/bin/env python3
"""
DQIII8 — Confidence Gate (Selective RAG)

Decides whether retrieved chunks should be injected into a prompt.
Injecting low-value chunks hurts well-trained models (natural_sciences −1.16,
formal_sciences −0.44 in DQ benchmarks).

Rules (evaluated in order — first match wins):
  1. Tier C (local small model): ALWAYS enrich — needs all help available.
  2. No chunks:                  never enrich — nothing to inject.
  3. max score < 0.20:           never enrich — chunks are irrelevant noise.
  4. Tier B + no specific data:  skip — 70B cloud model already knows this.
  5. Otherwise:                  enrich.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def should_enrich(
    prompt: str,
    domain: str,
    chunks: list[dict],
    tier: int,
) -> bool:
    """Return True if chunks should be injected, False if prompt is better alone.

    Parameters
    ----------
    prompt  : original user prompt (unused in logic, kept for future hooks)
    domain  : classified domain (e.g. 'social_sciences')
    chunks  : list[dict] from get_relevant_chunks() — each has 'text' and 'score'
    tier    : 1=Tier C (local), 2=Tier B (cloud free), 3=Tier A (paid)
    """
    # Rule 1: Tier C always benefits from enrichment
    if tier == 1:
        return True

    # Rule 2: nothing retrieved
    if not chunks:
        return False

    # Rule 3: all chunks are below relevance floor
    max_score = max(c.get("score", 0.0) for c in chunks)
    if max_score < 0.20:
        return False

    # Rule 4: Tier B — only enrich when at least one chunk has specific data
    if tier == 2:
        try:
            from intent_amplifier import has_specific_data
        except ImportError:
            return True  # cannot evaluate — default to enriching
        specific = [c for c in chunks if has_specific_data(c.get("text", ""))]
        if not specific:
            return False

    return True
