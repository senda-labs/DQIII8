#!/usr/bin/env python3
"""
backfill_routing_feedback.py — One-shot warm-start for routing_feedback table.

Reads 30 days of agent_actions and inserts inferred routing_feedback rows
so routing_analyzer.py has mass-critical data without waiting for organic fills.

Safety: exits if routing_feedback already has > 50 rows (already backfilled).

Usage:
    python3 bin/tools/backfill_routing_feedback.py
    python3 bin/tools/backfill_routing_feedback.py --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parent.parent.parent / "database" / "jarvis_metrics.db"

# Agent → domain mapping (matches domain_agent_map.json domains)
_AGENT_DOMAIN: dict[str, str] = {
    "finance-specialist": "social_sciences",
    "economics-specialist": "social_sciences",
    "marketing-specialist": "social_sciences",
    "legal-specialist": "social_sciences",
    "python-specialist": "applied_sciences",
    "web-specialist": "applied_sciences",
    "git-specialist": "applied_sciences",
    "ai-ml-specialist": "applied_sciences",
    "content-automator": "applied_sciences",
    "software-specialist": "applied_sciences",
    "math-specialist": "formal_sciences",
    "algo-specialist": "formal_sciences",
    "stats-specialist": "formal_sciences",
    "logic-specialist": "formal_sciences",
    "biology-specialist": "natural_sciences",
    "chemistry-specialist": "natural_sciences",
    "physics-specialist": "natural_sciences",
    "nutrition-specialist": "natural_sciences",
    "writing-specialist": "humanities_arts",
    "history-specialist": "humanities_arts",
    "philosophy-specialist": "humanities_arts",
    "language-specialist": "humanities_arts",
}


# Model substring → tier letter (A/B/C)
def _infer_tier(tier_col: str, model_used: str, agent_name: str = "") -> str:
    if tier_col and tier_col not in ("unknown", ""):
        return tier_col  # trust the stored value
    # Check both model_used and agent_name (backfill uses agent_name as fallback)
    combined = ((model_used or "") + " " + (agent_name or "")).lower()
    if "claude" in combined or "anthropic" in combined:
        return "A"
    if (
        "llama" in combined
        or "groq" in combined
        or "openrouter" in combined
        or "gpt" in combined
    ):
        return "B"
    if "qwen" in combined or "ollama" in combined:
        return "C"
    return "B"  # default fallback to cloud-free


def backfill(dry_run: bool = False) -> None:
    if not DB.exists():
        print(f"[BACKFILL] DB not found: {DB}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(DB), timeout=5)
    conn.row_factory = sqlite3.Row

    # Safety guard — skip if already backfilled
    existing = conn.execute("SELECT COUNT(*) FROM routing_feedback").fetchone()[0]
    if existing > 50:
        print(
            f"[BACKFILL] routing_feedback already has {existing} rows — skipping. "
            f"Delete rows manually to re-run."
        )
        conn.close()
        return

    rows = conn.execute("""
        SELECT agent_name, model_used, tier, domain, success, duration_ms, timestamp
        FROM agent_actions
        WHERE timestamp > datetime('now', '-30 days')
          AND success IS NOT NULL
          AND duration_ms IS NOT NULL
        ORDER BY timestamp
        """).fetchall()

    print(f"[BACKFILL] Source rows from agent_actions (30d): {len(rows)}")

    inserted = skipped = 0
    for r in rows:
        agent_name = r["agent_name"] or "unknown"
        model_used = r["model_used"] or ""
        tier_col = r["tier"] or ""
        domain_col = r["domain"] or ""
        ts = r["timestamp"]

        tier = _infer_tier(tier_col, model_used, agent_name)

        # Domain: use stored value if meaningful, else infer from agent name
        domain = domain_col if domain_col and domain_col != "unknown" else None
        if not domain:
            domain = _AGENT_DOMAIN.get(agent_name)

        prompt_hash = hashlib.md5(
            f"{agent_name}:{model_used}:{ts}".encode()
        ).hexdigest()[:16]

        if dry_run:
            inserted += 1
            continue

        try:
            conn.execute(
                "INSERT INTO routing_feedback "
                "(prompt_hash, domain, tier_used, model_used, success, duration_ms, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    prompt_hash,
                    domain,
                    tier,
                    model_used or agent_name,
                    r["success"],
                    r["duration_ms"],
                    ts,
                ),
            )
            inserted += 1
        except Exception as e:
            skipped += 1
            if skipped <= 3:
                print(f"[BACKFILL] skip error: {e}", file=sys.stderr)

    if not dry_run:
        conn.commit()

    conn.close()
    prefix = "[BACKFILL dry-run]" if dry_run else "[BACKFILL]"
    print(f"{prefix} Inserted: {inserted} | Skipped: {skipped}")
    print(f"{prefix} routing_feedback ready for routing_analyzer.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill routing_feedback from agent_actions"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show count without inserting"
    )
    args = parser.parse_args()
    backfill(dry_run=args.dry_run)
