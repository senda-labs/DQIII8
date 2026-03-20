#!/usr/bin/env python3
"""
DQIII8 — Subscription / Budget Tracker

Tracks monthly API spend vs. a configurable budget cap.
Called by `j --status` and /api/subscription in the dashboard.

Usage:
    python3 bin/subscription.py
    python3 -c "from subscription import get_status; print(get_status())"
"""

import os
import sqlite3
from datetime import datetime
from pathlib import Path

JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB_PATH = JARVIS / "database" / "jarvis_metrics.db"


def get_monthly_budget() -> float:
    """Return monthly budget in USD. 0 = unlimited."""
    raw = os.environ.get("DQIII8_MONTHLY_BUDGET", "0")
    try:
        return float(raw)
    except ValueError:
        return 0.0


def get_usage_this_month() -> dict:
    """Return cost breakdown for the current calendar month."""
    if not DB_PATH.exists():
        return {"total_usd": 0.0, "by_tier": {}, "action_count": 0}

    now = datetime.now()
    month_start = f"{now.year}-{now.month:02d}-01"

    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    try:
        rows = conn.execute(
            """
            SELECT tier, SUM(estimated_cost_usd), COUNT(*)
            FROM agent_actions
            WHERE timestamp >= ?
            GROUP BY tier
            """,
            (month_start,),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()

    by_tier: dict[str, float] = {}
    total = 0.0
    action_count = 0
    for tier, cost, count in rows:
        cost = cost or 0.0
        by_tier[tier or "unknown"] = round(cost, 6)
        total += cost
        action_count += count or 0

    return {
        "total_usd": round(total, 6),
        "by_tier": by_tier,
        "action_count": action_count,
        "month": f"{now.year}-{now.month:02d}",
    }


def get_status() -> dict:
    """Return full subscription status dict."""
    budget = get_monthly_budget()
    usage = get_usage_this_month()
    total = usage["total_usd"]

    pct = (total / budget * 100) if budget > 0 else 0.0
    remaining = max(budget - total, 0.0) if budget > 0 else None
    warning = budget > 0 and pct >= 90

    return {
        "budget_usd": budget,
        "unlimited": budget == 0,
        "used_usd": total,
        "remaining_usd": remaining,
        "percent_used": round(pct, 1),
        "warning": warning,
        "month": usage["month"],
        "action_count": usage["action_count"],
        "by_tier": usage["by_tier"],
    }


def _bar(pct: float, width: int = 20) -> str:
    """Return a simple ASCII progress bar."""
    filled = int(pct / 100 * width)
    filled = min(filled, width)
    return "█" * filled + "░" * (width - filled)


def print_status() -> None:
    s = get_status()
    print("─── DQIII8 Subscription Status ───")
    if s["unlimited"]:
        print(f"  Budget  : unlimited")
        print(f"  Used    : ${s['used_usd']:.4f} this month ({s['month']})")
    else:
        bar = _bar(s["percent_used"])
        print(f"  Budget  : ${s['budget_usd']:.2f}/month")
        print(f"  Used    : ${s['used_usd']:.4f}  [{bar}]  {s['percent_used']:.1f}%")
        print(f"  Left    : ${s['remaining_usd']:.4f}")
        if s["warning"]:
            print("  WARNING : Budget >= 90% used — Tier A/S requests may exceed cap")

    print(f"  Actions : {s['action_count']} this month")
    if s["by_tier"]:
        for tier, cost in sorted(s["by_tier"].items()):
            print(f"    {tier:<10} ${cost:.4f}")
    print("──────────────────────────────────")


if __name__ == "__main__":
    # Load .env if present so DQIII8_MONTHLY_BUDGET is available
    env_path = JARVIS / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
    print_status()
