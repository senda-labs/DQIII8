#!/usr/bin/env python3
"""Simple rate limiter to prevent runaway API costs."""
import os
import sqlite3
from datetime import datetime
from pathlib import Path

JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB_PATH = JARVIS / "database" / "jarvis_metrics.db"

# Default daily limits by tier
DAILY_LIMITS = {
    "C": float("inf"),  # No limit for local
    "B": 500,           # 500 free cloud calls/day
    "A": 100,           # 100 paid calls/day
    "S": 20,            # 20 planning calls/day
    "S+": 5,            # 5 orchestration calls/day
}


def check_rate_limit(tier: str) -> tuple[bool, int, int]:
    """Check if tier has remaining capacity. Returns (allowed, used, limit)."""
    limit_raw = DAILY_LIMITS.get(tier, 100)
    limit = int(os.environ.get(f"DQIII8_LIMIT_{tier}", limit_raw))
    if limit_raw == float("inf"):
        return True, 0, limit

    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    today = datetime.now().strftime("%Y-%m-%d")
    used = conn.execute(
        "SELECT COUNT(*) FROM agent_actions WHERE tier = ? AND date(timestamp) = ?",
        (tier, today),
    ).fetchone()[0]
    conn.close()

    return (used < limit, used, limit)


def get_usage_summary() -> dict:
    """Get today's usage by tier."""
    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    today = datetime.now().strftime("%Y-%m-%d")
    rows = conn.execute(
        """SELECT tier, COUNT(*) as calls,
           ROUND(SUM(estimated_cost_usd), 4) as cost
           FROM agent_actions
           WHERE date(timestamp) = ?
           GROUP BY tier""",
        (today,),
    ).fetchall()
    conn.close()
    return {r[0]: {"calls": r[1], "cost": r[2]} for r in rows}


if __name__ == "__main__":
    print("Today's usage by tier:")
    for tier, data in get_usage_summary().items():
        allowed, used, limit = check_rate_limit(tier or "B")
        status = "OK" if allowed else "LIMIT REACHED"
        print(f"  Tier {tier}: {data['calls']} calls, ${data['cost']} — {status}")
