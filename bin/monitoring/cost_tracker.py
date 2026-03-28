#!/usr/bin/env python3
"""
cost_tracker.py — Token usage and cost report per tier.

Two data sources:
  - agent_actions: rows with real tokens_input/tokens_output (direct API calls)
  - routing_feedback: full query volume with tier labels (estimated tokens)

Savings vs baseline "everything through Sonnet" are estimated using
AVG_TOKENS_PER_QUERY where real token counts are unavailable.

Usage:
    python3 bin/monitoring/cost_tracker.py
    python3 bin/monitoring/cost_tracker.py --days 7
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB = Path(__file__).resolve().parent.parent.parent / "database" / "dqiii8_metrics.db"
OUT = (
    Path(__file__).resolve().parent.parent.parent
    / "tasks"
    / "audit"
    / "cost-report.json"
)

# Sonnet 4.6 pricing per 1k tokens
COST_INPUT_1K = 0.003  # $3 / 1M input
COST_OUTPUT_1K = 0.015  # $15 / 1M output

# Fallback: blended average when only total tokens are known (assumes 3:1 in:out ratio)
# 0.75 * $0.003 + 0.25 * $0.015 = $0.006 / 1k blended
COST_BLENDED_1K = 0.006

# Estimated tokens per query when no real data available
AVG_TOKENS_PER_QUERY = 2000

# Tier C / B cost: $0 (Ollama local / Groq free)
TIER_COST_PER_QUERY: dict[str, float] = {
    "A": AVG_TOKENS_PER_QUERY / 1000 * COST_BLENDED_1K,  # ~$0.012 per query
    "B": 0.0,
    "C": 0.0,
}

TIER_LABELS = {"A": "Sonnet (Anthropic)", "B": "Groq free", "C": "Ollama local"}


def collect_real_tokens(conn: sqlite3.Connection, since: str) -> dict:
    """Real token counts from agent_actions rows that have token data."""
    rows = conn.execute(
        """
        SELECT tier,
               COUNT(*)                            AS queries,
               SUM(tokens_input)                   AS tok_in,
               SUM(tokens_output)                  AS tok_out,
               SUM(estimated_cost_usd)             AS est_cost
        FROM agent_actions
        WHERE timestamp >= ?
          AND tokens_input > 0
        GROUP BY tier
        """,
        (since,),
    ).fetchall()
    return {
        r[0]: {
            "queries": r[1],
            "tokens_in": r[2] or 0,
            "tokens_out": r[3] or 0,
            "est_cost": r[4] or 0.0,
        }
        for r in rows
        if r[0]  # skip NULL tier
    }


def collect_routing_volume(conn: sqlite3.Connection, since: str) -> dict:
    """Full query volume from routing_feedback (includes Claude Code sessions)."""
    rows = conn.execute(
        """
        SELECT tier_used, COUNT(*) AS queries,
               ROUND(AVG(success) * 100, 1) AS ok_pct,
               ROUND(AVG(duration_ms) / 1000.0, 1) AS avg_sec
        FROM routing_feedback
        WHERE timestamp >= ?
        GROUP BY tier_used
        """,
        (since,),
    ).fetchall()
    return {
        r[0]: {"queries": r[1], "ok_pct": r[2], "avg_sec": r[3]} for r in rows if r[0]
    }


def generate_cost_report(days: int = 30) -> dict:
    if not DB.exists():
        print(f"[COST] DB not found: {DB}")
        return {}

    from datetime import timedelta

    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(str(DB), timeout=5)
    real = collect_real_tokens(conn, cutoff)
    volume = collect_routing_volume(conn, cutoff)
    conn.close()

    # Merge tiers from both sources
    all_tiers = sorted(set(list(real.keys()) + list(volume.keys())))

    total_queries = sum(v["queries"] for v in volume.values())
    actual_cost = 0.0
    baseline_cost = 0.0
    tier_breakdown = {}

    for tier in all_tiers:
        vol = volume.get(tier, {})
        queries = vol.get("queries", 0)

        # Estimated tokens always uses routing_feedback volume for consistency.
        # Real token data (122 rows) is too sparse to be representative.
        tokens_est = queries * AVG_TOKENS_PER_QUERY

        # Actual cost with DQ routing:
        #   Tier A = Sonnet API price (or $0 for Claude Code fixed-plan sessions)
        #   Tier B = $0 (Groq free tier)
        #   Tier C = $0 (Ollama local)
        real_cost = (tokens_est / 1000 * COST_BLENDED_1K) if tier == "A" else 0.0
        actual_cost += real_cost

        # Baseline: what this tier's queries would cost if all went through Sonnet
        base = tokens_est / 1000 * COST_BLENDED_1K
        baseline_cost += base

        tier_breakdown[tier] = {
            "label": TIER_LABELS.get(tier, tier),
            "queries": queries,
            "ok_pct": vol.get("ok_pct", 0.0),
            "avg_sec": vol.get("avg_sec", 0.0),
            "tokens_est": tokens_est,
            "actual_cost_usd": round(real_cost, 4),
            "baseline_cost_usd": round(base, 4),
            "savings_usd": round(base - real_cost, 4),
        }

    savings = baseline_cost - actual_cost
    savings_pct = (savings / baseline_cost * 100) if baseline_cost > 0 else 0.0

    # Print report
    print(f"\n{'='*56}")
    print(f"DQIII8 Cost Report — last {days} days ({now.strftime('%Y-%m-%d')})")
    print(f"{'='*56}")
    print(
        f"{'Tier':<6} {'Label':<22} {'Queries':>8} {'OK%':>6} {'AvgSec':>8} {'Cost':>10} {'Baseline':>10} {'Saved':>10}"
    )
    print(f"{'-'*6} {'-'*22} {'-'*8} {'-'*6} {'-'*8} {'-'*10} {'-'*10} {'-'*10}")
    for tier in sorted(tier_breakdown.keys()):
        b = tier_breakdown[tier]
        print(
            f"{tier:<6} {b['label']:<22} {b['queries']:>8,} {b['ok_pct']:>5.1f}%"
            f" {b['avg_sec']:>7.1f}s ${b['actual_cost_usd']:>9.4f}"
            f" ${b['baseline_cost_usd']:>9.4f} ${b['savings_usd']:>9.4f}"
        )
    print(f"{'='*56}")
    print(
        f"{'TOTAL':<6} {'':<22} {total_queries:>8,} {'':>6} {'':>8}"
        f" ${actual_cost:>9.4f} ${baseline_cost:>9.4f} ${savings:>9.4f}"
    )
    print(f"\nSavings vs all-Sonnet baseline: ${savings:.4f} ({savings_pct:.1f}%)")
    print(
        f"Note: tokens estimated at {AVG_TOKENS_PER_QUERY} avg/query where real data unavailable."
    )

    report = {
        "generated": now.isoformat(),
        "period_days": days,
        "total_queries": total_queries,
        "actual_cost_usd": round(actual_cost, 4),
        "baseline_cost_usd": round(baseline_cost, 4),
        "savings_usd": round(savings, 4),
        "savings_pct": round(savings_pct, 1),
        "tier_breakdown": tier_breakdown,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[COST] Report → {OUT}")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DQIII8 cost tracker")
    parser.add_argument("--days", type=int, default=30, help="Lookback period in days")
    args = parser.parse_args()
    generate_cost_report(args.days)
