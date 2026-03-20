#!/usr/bin/env python3
"""
DQ — Amplification Benchmark
=============================
Compares prompt quality WITH vs WITHOUT intent amplification across 10 test prompts.

Metrics per prompt:
  - prompt_length:       character count of the prompt sent to the model
  - subtask_coverage:    intent-related keywords present (0-1)
  - knowledge_present:   knowledge chunks injected (0 or 1)
  - domain_confidence:   top domain cosine score (0-1)
  - overall:             weighted composite score (0-1)

Usage:
    python3 bin/benchmark_amplification.py
    python3 bin/benchmark_amplification.py --save         # save JSON to database/benchmarks/
    python3 bin/benchmark_amplification.py --json         # print JSON output
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

BIN_DIR = Path(__file__).parent
JARVIS = _JARVIS_ROOT
if str(_JARVIS_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(_JARVIS_ROOT / "bin"))

from jal_common import load_env

load_env()

from intent_amplifier import amplify
from quality_scorer import grade, score_amplification_quality

# ── 10 test prompts covering different domains and intent types ────────────────

TEST_PROMPTS = [
    # Finance
    "Analyze the risk profile of a $100K portfolio: 60% SPY, 25% BND, 10% GLD, 5% BTC at 95% confidence",
    "Forecast next quarter revenue for a SaaS company with $50K MRR and 8% monthly growth",
    # Marketing
    "Create a marketing campaign for organic cleaning products targeting eco-conscious homeowners, $2000/month budget",
    "Compare SEO vs Google Ads for a local bakery with $500/month marketing budget",
    # Business
    "Create a business plan for a digital marketing agency specializing in cleaning products, starting with 5000 GBP",
    "Research the best strategies for bootstrapping a B2B SaaS startup to $10K MRR in 12 months",
    # Software engineering
    "Design a microservices architecture for a food delivery app handling 10,000 concurrent orders",
    "Debug this Python function that crashes on empty input with a KeyError exception",
    # Biology / health
    "Create a nutrition plan for a 28yo male, 182cm, 78kg, active lifestyle, goal: recomposition",
    # General / cross-domain
    "Explain how to validate a machine learning model's performance before deploying to production",
]

# ── Raw result builder (no amplification) ─────────────────────────────────────

def _raw_result(prompt: str) -> dict:
    """
    Constructs a minimal amplify()-shaped dict representing the raw prompt
    with no enrichment. Scores reflect what the model receives without amplification.
    """
    return {
        "original":    prompt,
        "amplified":   prompt,          # no enrichment
        "action":      "",
        "entity":      "",
        "niche":       "",
        "intent":      _detect_intent(prompt),
        "domains":     [],              # no domain scoring
        "tier":        1,
        "tier_label":  "local/Ollama",
        "chunks_used": 0,               # no knowledge chunks
        "routing":     None,
    }


def _detect_intent(prompt: str) -> str:
    """Minimal intent detection matching the amplifier's patterns."""
    p = prompt.lower()
    mapping = {
        "analyze": ["analiz", "review", "evaluat", "assess"],
        "generate": ["generat", "create", "crea", "produc", "write"],
        "optimize": ["optim", "improv", "refactor"],
        "debug": ["debug", "fix", "crash", "error", "bug"],
        "research": ["research", "investig", "find", "discover"],
        "summarize": ["summar", "condense", "brief"],
        "compare": ["compar", "vs", "versus", "differenc"],
        "forecast": ["forecast", "predict", "project", "estim"],
        "explain": ["explain", "describ", "clarif", "defin"],
        "transform": ["transform", "translat", "convert", "migrat"],
        "validate": ["validat", "verif", "check"],
        "plan": ["plan", "design", "architect"],
        "automate": ["automat", "pipeline", "schedul"],
        "report": ["report", "dashboar", "execut"],
    }
    for intent, keywords in mapping.items():
        if any(kw in p for kw in keywords):
            return intent
    return "generate"


# ── Benchmark runner ───────────────────────────────────────────────────────────

def run_benchmark(verbose: bool = False) -> list[dict]:
    results = []

    for i, prompt in enumerate(TEST_PROMPTS, 1):
        if verbose:
            print(f"  [{i:02d}/{len(TEST_PROMPTS)}] {prompt[:60]}...", file=sys.stderr)

        # Raw (no amplification)
        t0 = time.time()
        raw_result = _raw_result(prompt)
        raw_scores = score_amplification_quality(raw_result)
        raw_ms = round((time.time() - t0) * 1000, 1)

        # Amplified
        t0 = time.time()
        amp_result = amplify(prompt)
        amp_scores = score_amplification_quality(amp_result)
        amp_ms = round((time.time() - t0) * 1000, 1)

        delta_overall = round(amp_scores["overall"] - raw_scores["overall"], 4)
        delta_pct = round(delta_overall / max(raw_scores["overall"], 0.01) * 100, 1)

        results.append({
            "prompt":           prompt,
            "prompt_short":     prompt[:55] + "…" if len(prompt) > 55 else prompt,
            "intent":           amp_result["intent"],
            "tier":             amp_result["tier"],
            "raw": {
                "length":           len(raw_result["amplified"]),
                "subtask_coverage": raw_scores["subtask_coverage"],
                "knowledge_present":raw_scores["knowledge_present"],
                "domain_confidence":raw_scores["domain_confidence"],
                "overall":          raw_scores["overall"],
                "grade":            grade(raw_scores["overall"]),
                "ms":               raw_ms,
            },
            "amplified": {
                "length":           len(amp_result["amplified"]),
                "subtask_coverage": amp_scores["subtask_coverage"],
                "knowledge_present":amp_scores["knowledge_present"],
                "domain_confidence":amp_scores["domain_confidence"],
                "overall":          amp_scores["overall"],
                "grade":            grade(amp_scores["overall"]),
                "ms":               amp_ms,
                "chunks_used":      amp_result["chunks_used"],
            },
            "delta_overall":    delta_overall,
            "delta_pct":        delta_pct,
        })

    return results


# ── Output formatters ──────────────────────────────────────────────────────────

_COL_W = 57  # prompt column width

def print_table(results: list[dict]):
    sep = "─" * (_COL_W + 72)
    header = (
        f"{'Prompt':<{_COL_W}} "
        f"{'Intent':<9} "
        f"{'Raw':>5} "
        f"{'Amp':>5} "
        f"{'Δ':>6} "
        f"{'Raw len':>7} "
        f"{'Amp len':>7} "
        f"{'KNow':>5} "
        f"{'Dom':>5} "
        f"{'Grade':>5}"
    )

    print()
    print("╔══ AMPLIFICATION BENCHMARK ══════════════════════════════════════════════════════╗")
    print(f"  {len(results)} prompts  |  Scores: 0.0–1.0  |  Δ = amplified − raw")
    print("╚══════════════════════════════════════════════════════════════════════════════════╝")
    print()
    print(header)
    print(sep)

    deltas = []
    for r in results:
        raw = r["raw"]
        amp = r["amplified"]
        delta_sign = "+" if r["delta_overall"] >= 0 else ""
        print(
            f"{r['prompt_short']:<{_COL_W}} "
            f"{r['intent']:<9} "
            f"{raw['overall']:>5.2f} "
            f"{amp['overall']:>5.2f} "
            f"{delta_sign}{r['delta_overall']:>5.2f} "
            f"{raw['length']:>7} "
            f"{amp['length']:>7} "
            f"{amp['knowledge_present']:>5.1f} "
            f"{amp['domain_confidence']:>5.2f} "
            f"{raw['grade']}→{amp['grade']:>1}"
        )
        deltas.append(r["delta_overall"])

    print(sep)

    avg_raw = sum(r["raw"]["overall"] for r in results) / len(results)
    avg_amp = sum(r["amplified"]["overall"] for r in results) / len(results)
    avg_delta = sum(deltas) / len(deltas)
    avg_delta_sign = "+" if avg_delta >= 0 else ""
    avg_len_raw = sum(r["raw"]["length"] for r in results) // len(results)
    avg_len_amp = sum(r["amplified"]["length"] for r in results) // len(results)

    print(
        f"{'AVERAGE':<{_COL_W}} "
        f"{'':9} "
        f"{avg_raw:>5.2f} "
        f"{avg_amp:>5.2f} "
        f"{avg_delta_sign}{avg_delta:>5.2f} "
        f"{avg_len_raw:>7} "
        f"{avg_len_amp:>7}"
    )
    print()
    print(f"  Amplification boost: {avg_delta_sign}{avg_delta:.2f} overall  "
          f"({avg_delta_sign}{round(avg_delta / max(avg_raw, 0.01) * 100, 1)}%)")
    print(f"  Avg prompt length:  {avg_len_raw} chars (raw) → {avg_len_amp} chars (amplified)  "
          f"({round(avg_len_amp / max(avg_len_raw, 1), 1)}× expansion)")

    wins = sum(1 for d in deltas if d > 0)
    ties = sum(1 for d in deltas if d == 0)
    losses = sum(1 for d in deltas if d < 0)
    print(f"  Amplification wins: {wins}/{len(results)} prompts improved  "
          f"({ties} ties, {losses} regressions)")
    print()


def save_results(results: list[dict]) -> Path:
    out_dir = JARVIS / "database" / "benchmarks"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"amplification_benchmark_{ts}.json"

    summary = {
        "run_at": datetime.now().isoformat(),
        "n_prompts": len(results),
        "avg_raw_overall":      round(sum(r["raw"]["overall"] for r in results) / len(results), 4),
        "avg_amp_overall":      round(sum(r["amplified"]["overall"] for r in results) / len(results), 4),
        "avg_delta":            round(sum(r["delta_overall"] for r in results) / len(results), 4),
        "avg_len_raw":          sum(r["raw"]["length"] for r in results) // len(results),
        "avg_len_amplified":    sum(r["amplified"]["length"] for r in results) // len(results),
        "wins":                 sum(1 for r in results if r["delta_overall"] > 0),
        "ties":                 sum(1 for r in results if r["delta_overall"] == 0),
        "losses":               sum(1 for r in results if r["delta_overall"] < 0),
    }

    payload = {"summary": summary, "results": results}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return out_path


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Amplification quality benchmark")
    parser.add_argument("--save", action="store_true", help="Save results to database/benchmarks/")
    parser.add_argument("--json", action="store_true", dest="json_out", help="Print JSON output")
    parser.add_argument("--quiet", action="store_true", help="No progress output")
    args = parser.parse_args()

    print("Running benchmark…", file=sys.stderr)
    results = run_benchmark(verbose=not args.quiet)

    if args.json_out:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        print_table(results)

    if args.save:
        path = save_results(results)
        print(f"Results saved → {path}")


if __name__ == "__main__":
    main()
