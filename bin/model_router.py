#!/usr/bin/env python3
"""
DQIII8 — Dynamic Model Router

Queries model_satisfaction DB and recommends the best model for a task_type.

Usage:
    python3 bin/model_router.py [task_type]
    task_type: código|análisis|escritura|research|pipeline|trading|mixto

Output:
    <model_used> score: <X.XX> — <N> tasks
"""

import os
import sqlite3
import sys
from pathlib import Path

DB = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis")) / "database" / "jarvis_metrics.db"

# Defaults per type when insufficient data
DEFAULT_BY_TYPE: dict[str, tuple[str, str]] = {
    "código": ("tier1", "qwen2.5-coder:7b"),
    "pipeline": ("tier1", "qwen2.5-coder:7b"),
    "análisis": ("tier2", "llama-3.3-70b-versatile"),
    "research": ("tier2", "llama-3.3-70b-versatile"),
    "escritura": ("tier3", "claude-sonnet-4-6"),
    "trading": ("tier3", "claude-sonnet-4-6"),
    "mixto": ("tier3", "claude-sonnet-4-6"),
}

MIN_SAMPLES = 5
NEUTRAL_SCORE = 0.5


def get_recommendation(task_type: str) -> tuple[str, float, int]:
    """Returns (model_used, score, n_samples)."""
    if not DB.exists():
        tier, model = DEFAULT_BY_TYPE.get(task_type, ("tier3", "claude-sonnet-4-6"))
        return model, NEUTRAL_SCORE, 0

    try:
        conn = sqlite3.connect(str(DB), timeout=2)
        rows = conn.execute(
            """
            SELECT model_used, AVG(user_satisfaction), COUNT(*)
            FROM (
                SELECT model_used, user_satisfaction
                FROM model_satisfaction
                WHERE task_type = ?
                  AND user_satisfaction IS NOT NULL
                ORDER BY timestamp DESC
                LIMIT 20
            )
            GROUP BY model_used
            ORDER BY AVG(user_satisfaction) DESC
            """,
            (task_type,),
        ).fetchall()
        conn.close()
    except Exception:
        rows = []

    if rows:
        best_model, best_score, n = rows[0]
        if n >= MIN_SAMPLES:
            return best_model, round(best_score, 2), n
        # Fewer than 5 samples — blend with neutral to avoid overconfidence
        blended = round((best_score * n + NEUTRAL_SCORE * (MIN_SAMPLES - n)) / MIN_SAMPLES, 2)
        return best_model, blended, n

    # No data → use static default
    tier, model = DEFAULT_BY_TYPE.get(task_type, ("tier3", "claude-sonnet-4-6"))
    return model, NEUTRAL_SCORE, 0


def main() -> None:
    task_type = sys.argv[1] if len(sys.argv) > 1 else "código"
    model, score, n = get_recommendation(task_type)
    label = f"{n} tasks" if n > 0 else "no data"
    print(f"{model} score: {score:.2f} — {label}")


if __name__ == "__main__":
    main()
