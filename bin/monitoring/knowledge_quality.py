#!/usr/bin/env python3
"""
knowledge_quality.py — Monthly knowledge chunk quality analysis.

Reads knowledge_usage table to compute per-source success rates.
Marks chunks with < 50% success rate (>= 5 uses) as "low quality"
and writes a report to tasks/audit/knowledge-quality.md.

Also scans agent_actions for domains with high knowledge_chunks_used
but low success_rate, to correlate enrichment with outcomes.

Usage:
    python3 bin/monitoring/knowledge_quality.py
"""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DQIII8_ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
DB = DQIII8_ROOT / "database" / "dqiii8_metrics.db"
OUT = DQIII8_ROOT / "tasks" / "audit" / "knowledge-quality.md"

NOW = datetime.now(timezone.utc)
SINCE = (NOW - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
MIN_USES = 5
QUALITY_THRESHOLD = 0.50


def analyze_chunk_usage(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            chunk_source,
            COUNT(*)         AS total_uses,
            SUM(action_success) AS successes,
            ROUND(AVG(relevance_score), 3) AS avg_relevance
        FROM knowledge_usage
        WHERE timestamp >= ?
        GROUP BY chunk_source
        HAVING total_uses >= ?
        ORDER BY total_uses DESC
        """,
        (SINCE, MIN_USES),
    ).fetchall()

    results = []
    for r in rows:
        total = r["total_uses"]
        ok = r["successes"] or 0
        sr = ok / total if total > 0 else 0.0
        results.append(
            {
                "source": r["chunk_source"],
                "uses": total,
                "successes": ok,
                "success_rate": round(sr, 3),
                "avg_relevance": r["avg_relevance"] or 0.0,
                "quality": "LOW" if sr < QUALITY_THRESHOLD else "OK",
            }
        )
    return results


def analyze_enrichment_correlation(conn: sqlite3.Connection) -> list[dict]:
    """Correlate knowledge enrichment with action success by domain."""
    rows = conn.execute(
        """
        SELECT
            COALESCE(domain, 'unknown') AS domain,
            COUNT(*)                    AS total,
            SUM(success)                AS ok,
            SUM(CASE WHEN knowledge_chunks_used > 0 THEN 1 ELSE 0 END) AS enriched,
            SUM(CASE WHEN knowledge_chunks_used = 0 THEN 1 ELSE 0 END) AS plain,
            SUM(CASE WHEN knowledge_chunks_used > 0 AND success=1 THEN 1 ELSE 0 END) AS enriched_ok,
            SUM(CASE WHEN knowledge_chunks_used = 0 AND success=1 THEN 1 ELSE 0 END) AS plain_ok
        FROM agent_actions
        WHERE timestamp >= ?
          AND domain IS NOT NULL
        GROUP BY domain
        HAVING total >= 5
        ORDER BY enriched DESC
        """,
        (SINCE,),
    ).fetchall()

    results = []
    for r in rows:
        enriched = r["enriched"] or 0
        plain = r["plain"] or 0
        enriched_sr = (r["enriched_ok"] or 0) / enriched if enriched > 0 else None
        plain_sr = (r["plain_ok"] or 0) / plain if plain > 0 else None
        results.append(
            {
                "domain": r["domain"],
                "total": r["total"],
                "enriched_pct": (
                    round(enriched / r["total"], 2) if r["total"] > 0 else 0
                ),
                "enriched_success_rate": (
                    round(enriched_sr, 3) if enriched_sr is not None else None
                ),
                "plain_success_rate": (
                    round(plain_sr, 3) if plain_sr is not None else None
                ),
            }
        )
    return results


def write_report(chunks: list[dict], correlations: list[dict]) -> None:
    today = NOW.strftime("%Y-%m-%d")
    low_quality = [c for c in chunks if c["quality"] == "LOW"]

    lines = [
        f"# DQIII8 — Knowledge Quality Report",
        f"> Generated: {today} | Period: last 30 days | Tool: knowledge_quality.py",
        "",
        "## Summary",
        f"- Chunks analyzed (>={MIN_USES} uses): {len(chunks)}",
        f"- Low quality (success_rate < {QUALITY_THRESHOLD:.0%}): {len(low_quality)}",
        f"- Domains correlated: {len(correlations)}",
        "",
    ]

    if chunks:
        lines += [
            "## Chunk Quality (by source file)",
            "",
            "| Source | Uses | Success% | Avg Relevance | Quality |",
            "|--------|------|----------|---------------|---------|",
        ]
        for c in chunks:
            lines.append(
                f"| {Path(c['source']).name} | {c['uses']} | "
                f"{c['success_rate']:.0%} | {c['avg_relevance']:.3f} | {c['quality']} |"
            )
        lines.append("")

        if low_quality:
            lines += [
                "### Low Quality Chunks — Action Required",
                "",
            ]
            for c in low_quality:
                lines.append(
                    f"- **{c['source']}**: {c['success_rate']:.0%} success "
                    f"over {c['uses']} uses → review or replace content"
                )
            lines.append("")
    else:
        lines += [
            "## Chunk Quality",
            "",
            "_No chunk usage data yet — knowledge_usage table is empty._",
            "_Chunks will be tracked once knowledge_enricher logs usage to DB._",
            "",
        ]

    if correlations:
        lines += [
            "## Enrichment vs Plain Routing (by domain)",
            "",
            "| Domain | Enriched% | Enriched SR | Plain SR | Delta |",
            "|--------|-----------|-------------|----------|-------|",
        ]
        for c in correlations:
            esr = (
                f"{c['enriched_success_rate']:.0%}"
                if c["enriched_success_rate"] is not None
                else "n/a"
            )
            psr = (
                f"{c['plain_success_rate']:.0%}"
                if c["plain_success_rate"] is not None
                else "n/a"
            )
            if (
                c["enriched_success_rate"] is not None
                and c["plain_success_rate"] is not None
            ):
                delta = c["enriched_success_rate"] - c["plain_success_rate"]
                delta_str = f"{delta:+.0%}"
            else:
                delta_str = "n/a"
            lines.append(
                f"| {c['domain']} | {c['enriched_pct']:.0%} | {esr} | {psr} | {delta_str} |"
            )
        lines.append("")

    lines += [
        "## Recommendations",
        "",
    ]
    if low_quality:
        for c in low_quality:
            lines.append(
                f"- Review `{c['source']}` — {c['success_rate']:.0%} success rate "
                f"suggests content may be misleading or outdated"
            )
    else:
        lines.append("- No low-quality chunks detected — knowledge base health is good")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    print(f"[knowledge_quality] Starting — {NOW.strftime('%Y-%m-%d %H:%M UTC')}")
    if not DB.exists():
        print(f"[knowledge_quality] DB not found: {DB}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(DB), timeout=5)
    conn.row_factory = sqlite3.Row

    chunks = analyze_chunk_usage(conn)
    correlations = analyze_enrichment_correlation(conn)
    conn.close()

    write_report(chunks, correlations)

    low = sum(1 for c in chunks if c["quality"] == "LOW")
    print(f"[knowledge_quality] {len(chunks)} chunks, {low} low-quality → {OUT}")


if __name__ == "__main__":
    main()
