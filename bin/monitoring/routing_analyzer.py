#!/usr/bin/env python3
"""
routing_analyzer.py — Weekly routing accuracy analysis.

Reads agent_actions for the last 30 days to compute per-(domain, tier)
success rates and average latency. Generates routing_recommendations.json
with actionable suggestions when a tier underperforms for a domain.

Thresholds:
  - success_rate < 0.80 with >= 10 samples → recommend escalation
  - avg_duration_ms > 60_000 with >= 10 samples → recommend faster tier
  - tier with 0% success → alert immediately

Usage:
    python3 bin/monitoring/routing_analyzer.py
    python3 bin/monitoring/routing_analyzer.py --days 7
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DQIII8_ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
DB = DQIII8_ROOT / "database" / "dqiii8_metrics.db"
OUT = DQIII8_ROOT / "tasks" / "routing_recommendations.json"

DAYS = 30
for arg in sys.argv[1:]:
    if arg.startswith("--days="):
        DAYS = int(arg.split("=")[1])
    elif arg == "--days" and len(sys.argv) > sys.argv.index(arg) + 1:
        DAYS = int(sys.argv[sys.argv.index(arg) + 1])

NOW = datetime.now(timezone.utc)
SINCE = (NOW - timedelta(days=DAYS)).strftime("%Y-%m-%d %H:%M:%S")

MIN_SAMPLES = 10
SUCCESS_THRESHOLD = 0.80
DURATION_THRESHOLD_MS = 60_000  # 60s


def analyze() -> list[dict]:
    if not DB.exists():
        print(f"[routing_analyzer] DB not found: {DB}", file=sys.stderr)
        return []

    conn = sqlite3.connect(str(DB), timeout=5)
    conn.row_factory = sqlite3.Row

    # Primary source: agent_actions (has tier, domain, model_used, success, duration_ms)
    rows = conn.execute(
        """
        SELECT
            COALESCE(domain, 'unknown')      AS domain,
            COALESCE(tier, 'unknown')        AS tier,
            COALESCE(model_used, 'unknown')  AS model,
            COUNT(*)                         AS total,
            SUM(success)                     AS ok,
            ROUND(AVG(duration_ms), 0)       AS avg_ms
        FROM agent_actions
        WHERE timestamp >= ?
          AND domain IS NOT NULL
          AND tier IS NOT NULL
          AND tier != 'unknown'
        GROUP BY domain, tier
        ORDER BY total DESC
        """,
        (SINCE,),
    ).fetchall()

    # Also pull from routing_feedback if populated
    rf_rows = conn.execute(
        """
        SELECT
            COALESCE(domain, 'unknown')    AS domain,
            COALESCE(tier_used, 'unknown') AS tier,
            COALESCE(model_used, 'unknown') AS model,
            COUNT(*)                       AS total,
            SUM(success)                   AS ok,
            ROUND(AVG(duration_ms), 0)     AS avg_ms
        FROM routing_feedback
        WHERE timestamp >= ?
          AND domain IS NOT NULL
        GROUP BY domain, tier_used
        """,
        (SINCE,),
    ).fetchall()

    conn.close()

    # Merge both sources keyed by (domain, tier)
    merged: dict[tuple, dict] = {}
    for src in (rows, rf_rows):
        for r in src:
            key = (r["domain"], r["tier"])
            if key not in merged:
                merged[key] = {
                    "domain": r["domain"],
                    "tier": r["tier"],
                    "model": r["model"],
                    "total": 0,
                    "ok": 0,
                    "avg_ms": r["avg_ms"] or 0,
                }
            merged[key]["total"] += r["total"] or 0
            merged[key]["ok"] += r["ok"] or 0

    recommendations: list[dict] = []
    stats: list[dict] = []

    for (domain, tier), m in sorted(merged.items()):
        total = m["total"]
        ok = m["ok"] or 0
        sr = ok / total if total > 0 else 0.0
        avg_ms = m["avg_ms"]

        stats.append(
            {
                "domain": domain,
                "tier": tier,
                "model": m["model"],
                "total": total,
                "success_rate": round(sr, 3),
                "avg_ms": int(avg_ms or 0),
            }
        )

        if total < MIN_SAMPLES:
            continue  # not enough data

        if sr == 0.0:
            recommendations.append(
                {
                    "severity": "CRITICAL",
                    "domain": domain,
                    "tier": tier,
                    "model": m["model"],
                    "issue": f"0% success rate over {total} calls — tier completely failing",
                    "action": f"Immediately disable {tier} for {domain}, route to higher tier",
                }
            )
        elif sr < SUCCESS_THRESHOLD:
            recommendations.append(
                {
                    "severity": "WARN",
                    "domain": domain,
                    "tier": tier,
                    "model": m["model"],
                    "issue": f"success_rate={sr:.0%} ({ok}/{total}) below threshold {SUCCESS_THRESHOLD:.0%}",
                    "action": f"Consider escalating {domain} to higher tier",
                }
            )

        if avg_ms > DURATION_THRESHOLD_MS:
            recommendations.append(
                {
                    "severity": "WARN",
                    "domain": domain,
                    "tier": tier,
                    "model": m["model"],
                    "issue": f"avg_duration={avg_ms/1000:.0f}s exceeds {DURATION_THRESHOLD_MS//1000}s threshold",
                    "action": f"Consider routing {domain} to a lower-latency provider",
                }
            )

    return recommendations, stats


def main() -> None:
    print(
        f"[routing_analyzer] Analyzing last {DAYS} days — {NOW.strftime('%Y-%m-%d %H:%M UTC')}"
    )

    recommendations, stats = analyze()

    output = {
        "generated": NOW.isoformat(),
        "period_days": DAYS,
        "stats": stats,
        "recommendations": recommendations,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[routing_analyzer] {len(stats)} domain/tier combos analyzed")
    print(f"[routing_analyzer] {len(recommendations)} recommendations → {OUT}")

    for rec in recommendations:
        sev = rec["severity"]
        print(f"  [{sev}] {rec['domain']}/{rec['tier']}: {rec['issue']}")

    if not recommendations:
        print("[routing_analyzer] No routing issues detected")


if __name__ == "__main__":
    main()
