#!/usr/bin/env python3
"""
DQ — Amplification Quality Scorer

Scores the quality of an amplified prompt result from intent_amplifier.amplify().

Dimensions:
  - subtask_coverage:   subtask keywords from the detected intent present in the prompt
  - prompt_richness:    length indicates enrichment happened
  - knowledge_present:  knowledge chunks were retrieved and injected
  - domain_confidence:  how strongly the top domain scored

Usage:
    from quality_scorer import score_amplification_quality
    result = amplify("Create a business plan")
    scores = score_amplification_quality(result)
    print(scores["overall"])   # 0.0 – 1.0

    python3 bin/quality_scorer.py "your prompt here"
"""

import sys
from pathlib import Path

_JARVIS_ROOT = Path(os.environ.get('JARVIS_ROOT', str(Path(__file__).parent.parent.parent)))
for _d in [_JARVIS_ROOT / 'bin' / s for s in ['', 'core', 'agents', 'monitoring', 'tools', 'ui']]:
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

# Subtask keywords associated with each intent pattern (mirrors dashboard._INTENT_SUBTASKS)
_INTENT_SUBTASKS: dict = {
    "analyze":   ["collection", "analysis", "pattern", "report"],
    "generate":  ["requirements", "draft", "review", "finalization"],
    "optimize":  ["profiling", "bottleneck", "refactor", "benchmark"],
    "debug":     ["reproduction", "root cause", "fix", "regression"],
    "research":  ["discovery", "extraction", "analysis", "synthesis"],
    "summarize": ["parsing", "key points", "summary"],
    "compare":   ["criteria", "collection", "analysis", "recommendation"],
    "forecast":  ["historical", "model", "projection", "confidence"],
    "explain":   ["decomposition", "examples", "analogies", "summary"],
    "transform": ["parsing", "mapping", "transformation", "validation"],
    "validate":  ["schema", "rules", "edge cases", "report"],
    "plan":      ["requirements", "architecture", "breakdown", "timeline"],
    "automate":  ["mapping", "script", "testing", "deployment"],
    "report":    ["collection", "analysis", "visualization", "summary"],
}


def score_amplification_quality(result: dict) -> dict:
    """
    Score an amplify() result dict on four quality dimensions.

    Args:
        result: dict returned by intent_amplifier.amplify()

    Returns:
        {
          "subtask_coverage":  float 0-1,
          "prompt_richness":   float 0-1,
          "knowledge_present": float 0-1,
          "domain_confidence": float 0-1,
          "overall":           float 0-1,
        }
    """
    amplified = result.get("amplified", "")
    intent = result.get("intent", "")
    chunks_used = result.get("chunks_used", 0)
    domains = result.get("domains", [])

    scores: dict = {
        "subtask_coverage": 0.0,
        "prompt_richness": 0.0,
        "knowledge_present": 0.0,
        "domain_confidence": 0.0,
    }

    # 1. Subtask coverage: how many intent-related keywords appear in the amplified prompt
    subtasks = _INTENT_SUBTASKS.get(intent, [])
    if subtasks:
        prompt_lower = amplified.lower()
        mentioned = sum(1 for kw in subtasks if kw in prompt_lower)
        scores["subtask_coverage"] = mentioned / len(subtasks)
    else:
        # Unknown intent — neutral score
        scores["subtask_coverage"] = 0.5

    # 2. Prompt richness: longer = more enrichment
    length = len(amplified)
    if length > 2000:
        scores["prompt_richness"] = 1.0
    elif length > 1000:
        scores["prompt_richness"] = 0.7
    elif length > 500:
        scores["prompt_richness"] = 0.4
    elif length > 100:
        scores["prompt_richness"] = 0.2

    # 3. Knowledge present: chunks were retrieved
    scores["knowledge_present"] = 1.0 if chunks_used > 0 else 0.0

    # 4. Domain confidence: score of top domain (already 0-1 cosine)
    if domains:
        top_score = domains[0].get("score", 0.0)
        scores["domain_confidence"] = min(float(top_score), 1.0)

    # Weighted overall
    weights = {
        "subtask_coverage": 0.30,
        "prompt_richness":  0.20,
        "knowledge_present": 0.30,
        "domain_confidence": 0.20,
    }
    scores["overall"] = round(
        sum(scores[k] * weights[k] for k in weights), 4
    )

    return scores


def grade(overall: float) -> str:
    """Return a letter grade for the overall score."""
    if overall >= 0.85:
        return "A"
    if overall >= 0.70:
        return "B"
    if overall >= 0.50:
        return "C"
    if overall >= 0.30:
        return "D"
    return "F"


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    from jal_common import load_env
    load_env()

    if len(sys.argv) < 2:
        print('Usage: python3 bin/quality_scorer.py "<prompt>"', file=sys.stderr)
        sys.exit(1)

    prompt = " ".join(sys.argv[1:])

    from intent_amplifier import amplify
    result = amplify(prompt)
    scores = score_amplification_quality(result)

    print(f"\nPrompt: {prompt[:80]}")
    print(f"Intent: {result['intent']}  |  Tier: {result['tier']} ({result['tier_label']})")
    print(f"Chunks used: {result['chunks_used']}")
    print()
    print("Quality scores:")
    for key in ("subtask_coverage", "prompt_richness", "knowledge_present", "domain_confidence"):
        bar = "█" * int(scores[key] * 20) + "░" * (20 - int(scores[key] * 20))
        print(f"  {key:22s} {bar} {scores[key]:.2f}")
    print(f"\n  Overall: {scores['overall']:.2f}  [{grade(scores['overall'])}]")


if __name__ == "__main__":
    main()
