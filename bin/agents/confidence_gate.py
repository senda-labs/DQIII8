#!/usr/bin/env python3
"""
DQIII8 — Confidence Gate (Selective RAG)

Decides whether retrieved chunks should be injected into a prompt.

Rules (evaluated in order — first match wins):
  1. Tier C (local small model): ALWAYS enrich — needs all help available.
  2. No chunks:                  never enrich — nothing to inject.
  3. max score < 0.30:           never enrich — chunks are irrelevant noise.
  4. Tier B + no specific data:  skip — 70B cloud model already knows general facts.
  5. Tier A + score < 0.55:      skip — frontier model hurt by loosely-related data.
  6. Otherwise:                  enrich.

Benchmark evidence (2026-03-25):
  DQ OFF avg: 15.4/50  DQ ON avg: 14.9/50  (delta -0.5, 9/20 tasks hurt)
  Root cause: chunks with score 0.25-0.45 injected irrelevant context, increasing
  hallucination confidence (ICLR 2025, Joren et al. "Sufficient Context").
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Similarity threshold for Tier A (frontier) — only inject highly relevant specific data
_TIER_A_SIM_THRESHOLD = 0.55
# Minimum similarity floor — universal floor applied before tier-specific rules (Rule 3)
_MIN_SIM_FLOOR = 0.30


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
    tier    : 1=Tier C (local) — always enriches
              2=Tier B (cloud free) — enriches only if chunks have specific/numerical data
              3=Tier A (paid) — enriches only if score≥0.55 AND chunks have specific data
    """
    # Rule 1: Tier C always benefits from enrichment (small local model needs context)
    if tier == 1:
        return True

    # Rule 2: nothing retrieved
    if not chunks:
        return False

    # Rule 3: all chunks below relevance floor
    max_score = max(c.get("score", 0.0) for c in chunks)
    if max_score < _MIN_SIM_FLOOR:
        return False

    # Rule 4: Tier B — only enrich when at least one chunk has specific/numerical data
    if tier == 2:
        try:
            from intent_amplifier import has_specific_data
        except ImportError:
            return True  # cannot evaluate — default to enriching
        specific = [c for c in chunks if has_specific_data(c.get("text", ""))]
        if not specific:
            return False

    # Rule 5: Tier A — require high similarity AND specific data
    # Frontier models are hurt most by loosely-related context (ICLR 2025 finding)
    if tier == 3:
        if max_score < _TIER_A_SIM_THRESHOLD:
            return False
        try:
            from intent_amplifier import has_specific_data
        except ImportError:
            return True
        specific = [c for c in chunks if has_specific_data(c.get("text", ""))]
        if not specific:
            return False

    return True
