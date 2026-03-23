#!/usr/bin/env python3
"""
DQ ML Model Selector — Learns from historical data to recommend optimal tier.

Algorithm: Statistics-based decision tree (no ML libraries needed).
Learns: avg latency, avg tokens, success rate per (domain, tier) pair.
Recommends: cheapest tier that meets the user's constraints (latency, quality).

Training: reads agent_actions table.
Inference: <1ms (dict lookup).
Retraining: automatic on each call if data is stale (>1 hour).

Usage:
    python3 bin/ml_selector.py "Write a Python function"
    python3 bin/ml_selector.py --train
    python3 bin/ml_selector.py --stats
    python3 bin/ml_selector.py --test
"""

import os
import sys
import json
import time
import sqlite3
from pathlib import Path
from datetime import datetime

JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
for _d in [JARVIS / "bin" / s for s in ["", "core", "agents", "monitoring", "tools", "ui"]]:
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

from db import get_db

# ── Configuration ─────────────────────────────────────────────────────────

TIER_COSTS = {"C": 0.0, "B": 0.0, "A": 0.03, "S": 0.30, "S+": 1.00}
TIER_PRIORITY = {"C": 1, "B": 2, "A": 3, "S": 4, "S+": 5}

PROFILES = {
    "fast":     {"max_latency_ms": 5_000,   "min_success_rate": 0.90},
    "balanced": {"max_latency_ms": 30_000,  "min_success_rate": 0.95},
    "cheap":    {"max_latency_ms": 120_000, "min_success_rate": 0.85},
    "quality":  {"max_latency_ms": 60_000,  "min_success_rate": 0.98},
}
DEFAULT_PROFILE = "balanced"
RETRAIN_INTERVAL = 3600  # seconds

DOMAIN_KEYWORDS = {
    "python_code":       ["python", "function", "class", "def ", "import", "pip"],
    "algorithms":        ["algorithm", "sort", "search", "binary", "tree", "graph", "bfs", "dfs"],
    "database_sql":      ["sql", "query", "database", "select", "join", "table", "index"],
    "devops_infra":      ["docker", "kubernetes", "nginx", "deploy", "ci/cd", "github actions"],
    "web_development":   ["html", "css", "javascript", "react", "api", "frontend", "backend"],
    "finance_economics": ["finance", "stock", "portfolio", "var", "capm", "npv", "irr", "risk"],
    "business_marketing":["marketing", "business", "startup", "customer", "sales", "strategy"],
    "science_math":      ["theorem", "probability", "statistics", "calculus", "derivative", "bayes"],
    "writing_creative":  ["write", "story", "novel", "chapter", "character", "creative"],
    "general_knowledge": ["explain", "what is", "how does", "difference between"],
}

# ── Model state ────────────────────────────────────────────────────────────

_model = {
    "stats": {},        # {(domain, tier): {avg_ms, avg_tokens, success_rate, count}}
    "domain_map": {},   # {domain: [sorted tier dicts]}
    "global_stats": {}, # {tier: {avg_ms, avg_tokens, success_rate, count}}
    "trained_at": 0,
    "total_records": 0,
}


# ── Training ───────────────────────────────────────────────────────────────

def train() -> dict:
    """Read agent_actions and build performance stats by (domain, tier)."""
    global _model

    with get_db() as conn:
        # Per (domain, tier) stats — minimum 3 records to be meaningful
        rows = conn.execute("""
            SELECT
                COALESCE(domain, 'unknown')  AS domain,
                COALESCE(tier,   'unknown')  AS tier,
                COUNT(*)                     AS cnt,
                AVG(duration_ms)             AS avg_ms,
                AVG(tokens_output)           AS avg_tokens_out,
                AVG(tokens_input)            AS avg_tokens_in,
                AVG(success)                 AS success_rate,
                MIN(duration_ms)             AS min_ms,
                MAX(duration_ms)             AS max_ms
            FROM agent_actions
            WHERE timestamp > datetime('now', '-30 days')
            GROUP BY domain, tier
            HAVING COUNT(*) >= 3
        """).fetchall()

        stats = {}
        for r in rows:
            key = (r["domain"], r["tier"])
            stats[key] = {
                "count":          r["cnt"],
                "avg_ms":         round(r["avg_ms"]         or 0),
                "avg_tokens_out": round(r["avg_tokens_out"] or 0),
                "avg_tokens_in":  round(r["avg_tokens_in"]  or 0),
                "success_rate":   round(r["success_rate"]   or 0, 3),
                "min_ms":         r["min_ms"] or 0,
                "max_ms":         r["max_ms"] or 0,
            }

        # Global per-tier stats (all domains)
        global_rows = conn.execute("""
            SELECT
                COALESCE(tier, 'unknown') AS tier,
                COUNT(*)                  AS cnt,
                AVG(duration_ms)          AS avg_ms,
                AVG(tokens_output)        AS avg_tokens_out,
                AVG(success)              AS success_rate
            FROM agent_actions
            WHERE timestamp > datetime('now', '-30 days')
            GROUP BY tier
        """).fetchall()

        global_stats = {}
        for r in global_rows:
            global_stats[r["tier"]] = {
                "count":          r["cnt"],
                "avg_ms":         round(r["avg_ms"]         or 0),
                "avg_tokens_out": round(r["avg_tokens_out"] or 0),
                "success_rate":   round(r["success_rate"]   or 0, 3),
            }

        total = conn.execute(
            "SELECT COUNT(*) FROM agent_actions WHERE timestamp > datetime('now', '-30 days')"
        ).fetchone()[0]

    # Build per-domain sorted tier recommendations
    all_domains = {d for d, _ in stats}
    domain_map = {}

    for domain in all_domains:
        candidates = []
        for tier in TIER_COSTS:
            key = (domain, tier)
            if key not in stats:
                continue
            s = stats[key]
            # Composite score — lower = better
            cost_score      = TIER_PRIORITY.get(tier, 5) * 10     # 10–50
            latency_score   = min(s["avg_ms"] / 1000, 100)        # 0–100 (seconds capped)
            fail_penalty    = (1 - s["success_rate"]) * 100       # 0–100
            token_bonus     = -min(s["avg_tokens_out"] / 10, 50)  # −50–0 (more = better)

            composite = (
                cost_score    * 0.40 +
                latency_score * 0.30 +
                fail_penalty  * 0.20 +
                token_bonus   * 0.10
            )
            candidates.append({
                "tier":         tier,
                "score":        round(composite, 2),
                "avg_ms":       s["avg_ms"],
                "success_rate": s["success_rate"],
                "avg_tokens":   s["avg_tokens_out"],
                "count":        s["count"],
            })

        candidates.sort(key=lambda x: x["score"])
        domain_map[domain] = candidates

    _model = {
        "stats":         stats,
        "domain_map":    domain_map,
        "global_stats":  global_stats,
        "trained_at":    time.time(),
        "total_records": total,
    }
    return _model


def _ensure_trained():
    if (time.time() - _model["trained_at"]) > RETRAIN_INTERVAL:
        train()


# ── Domain detection ───────────────────────────────────────────────────────

def detect_domain(text: str) -> tuple[str, int]:
    """Return (domain, match_count) for a prompt using keyword matching."""
    lower = text.lower()
    best_domain, best_score = "unknown", 0
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in lower)
        if score > best_score:
            best_score, best_domain = score, domain
    return best_domain, best_score


# ── Inference ──────────────────────────────────────────────────────────────

def recommend(domain: str = "unknown", profile: str = DEFAULT_PROFILE) -> dict:
    """Return full recommendation dict for a given domain + constraint profile."""
    _ensure_trained()

    constraints = PROFILES.get(profile, PROFILES[DEFAULT_PROFILE])
    max_ms      = constraints["max_latency_ms"]
    min_success = constraints["min_success_rate"]

    candidates = _model["domain_map"].get(domain, [])

    if not candidates:
        # No domain-specific data — fall back to global tier stats
        candidates = [
            {
                "tier":         tier,
                "score":        TIER_PRIORITY.get(tier, 5) * 10,
                "avg_ms":       gs["avg_ms"],
                "success_rate": gs["success_rate"],
                "avg_tokens":   gs["avg_tokens_out"],
                "count":        gs["count"],
            }
            for tier, gs in _model["global_stats"].items()
        ]
        candidates.sort(key=lambda x: x["score"])
        confidence = "low"
    else:
        min_count  = min(c["count"] for c in candidates)
        confidence = "high" if min_count >= 20 else "medium" if min_count >= 5 else "low"

    # Filter by constraints
    valid = [c for c in candidates
             if c["avg_ms"] <= max_ms and c["success_rate"] >= min_success]

    if not valid:
        valid = candidates  # relax — return best available
        note = f" (constraints relaxed — no tier meets max {max_ms}ms + {min_success:.0%} success)"
    else:
        note = ""

    if not valid:
        return {
            "recommended_tier":      "B",
            "reason":                "No historical data. Defaulting to Tier B.",
            "alternatives":          ["C"],
            "predicted_latency_ms":  0,
            "predicted_success_rate":0.0,
            "predicted_cost":        0.0,
            "confidence":            "none",
            "data_points":           0,
        }

    best = valid[0]
    reasons = {
        "C": f"Tier C: free local inference, {best['avg_ms']/1000:.1f}s avg for {domain}",
        "B": f"Tier B: free cloud, {best['avg_ms']/1000:.1f}s avg ({best['success_rate']:.0%} success)",
        "A": f"Tier A: ~${TIER_COSTS['A']}/task, needed for quality on {domain}",
    }
    reason = reasons.get(best["tier"],
                         f"Tier {best['tier']} best for {domain}") + note

    return {
        "recommended_tier":      best["tier"],
        "reason":                reason,
        "alternatives":          [c["tier"] for c in valid[1:3]],
        "predicted_latency_ms":  best["avg_ms"],
        "predicted_success_rate":best["success_rate"],
        "predicted_cost":        TIER_COSTS.get(best["tier"], 0.0),
        "confidence":            confidence,
        "data_points":           best["count"],
    }


def recommend_for_prompt(prompt: str, profile: str = DEFAULT_PROFILE) -> dict:
    """Full pipeline: detect domain → recommend tier."""
    domain, domain_score = detect_domain(prompt)
    result = recommend(domain=domain, profile=profile)
    result["detected_domain"]   = domain
    result["domain_confidence"] = domain_score
    return result


def get_tier_recommendation(prompt: str, profile: str = DEFAULT_PROFILE) -> str:
    """Simple interface: returns just the tier letter. For use in routing."""
    return recommend_for_prompt(prompt, profile)["recommended_tier"]


# ── Stats display ──────────────────────────────────────────────────────────

def print_stats():
    _ensure_trained()
    m = _model
    ts = datetime.fromtimestamp(m["trained_at"]).strftime("%Y-%m-%d %H:%M:%S")

    print(f"\n{'='*70}")
    print(f"ML MODEL SELECTOR — Statistics")
    print(f"Trained : {ts}")
    print(f"Records : {m['total_records']} (last 30 days)")
    print(f"{'='*70}")

    print(f"\nGlobal tier performance:")
    print(f"  {'Tier':<6} {'Count':>6} {'Avg ms':>8} {'Avg tok':>8} {'Success':>8} {'Cost':>8}")
    print(f"  {'-'*6} {'-'*6} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
    for tier in ["C", "B", "A", "S", "S+"]:
        gs = m["global_stats"].get(tier)
        if gs:
            print(f"  {tier:<6} {gs['count']:>6d} {gs['avg_ms']:>7d}ms "
                  f"{gs['avg_tokens_out']:>7d} {gs['success_rate']:>7.1%} "
                  f"  ${TIER_COSTS.get(tier, 0):>5.2f}")

    print(f"\nPer-domain best tier:")
    for domain, tiers in sorted(m["domain_map"].items()):
        if tiers:
            best = tiers[0]
            alts = ", ".join(t["tier"] for t in tiers[1:3])
            print(f"  {domain:<22} → Tier {best['tier']} "
                  f"(score:{best['score']:.1f}, {best['avg_ms']}ms, "
                  f"{best['success_rate']:.0%}, n={best['count']})  "
                  f"alt:[{alts}]")

    print(f"\nSample profile sweep — 'Write a Python sorting function':")
    for pname in PROFILES:
        rec = recommend_for_prompt("Write a Python sorting function", pname)
        print(f"  {pname:<10} → Tier {rec['recommended_tier']}  "
              f"{rec['predicted_latency_ms']}ms  {rec['confidence']} confidence")


# ── CLI ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    if sys.argv[1] == "--train":
        m = train()
        print(f"Trained on {m['total_records']} records.")
        print(f"Domains with data : {len(m['domain_map'])}")
        print(f"Tiers seen        : {sorted(m['global_stats'].keys())}")

    elif sys.argv[1] == "--stats":
        print_stats()

    elif sys.argv[1] == "--test":
        train()
        tests = [
            ("Write a Python function to sort a list",          "python_code"),
            ("Explain the CAPM model and key assumptions",      "finance_economics"),
            ("Write chapter 1 of a sci-fi thriller novel",      "writing_creative"),
            ("Design a REST API with OAuth2 authentication",    "web_development"),
            ("Difference between SQL and NoSQL databases",      "database_sql"),
            ("Write a Dockerfile for a Flask app",             "devops_infra"),
            ("What is the central limit theorem",               "science_math"),
            ("Explain SWOT analysis for a coffee startup",      "business_marketing"),
            ("Implement merge sort with time complexity notes",  "algorithms"),
            ("How does HTTPS encryption work",                  "general_knowledge"),
        ]
        print(f"\n{'='*70}")
        print(f"DOMAIN DETECTION + TIER RECOMMENDATION TEST")
        print(f"{'='*70}")
        correct = 0
        for prompt, expected in tests:
            result = recommend_for_prompt(prompt)
            ok = result["detected_domain"] == expected
            correct += ok
            mark = "✓" if ok else "✗"
            print(f"  {mark} [{result['detected_domain']:<22}] "
                  f"Tier {result['recommended_tier']} "
                  f"({result['predicted_latency_ms']}ms, conf:{result['confidence']}) "
                  f"| {prompt[:45]}...")
        print(f"\n  Domain accuracy: {correct}/{len(tests)} ({correct/len(tests):.0%})")

    else:
        prompt = " ".join(sys.argv[1:])
        result = recommend_for_prompt(prompt)
        print(json.dumps(result, indent=2))
