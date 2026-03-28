#!/usr/bin/env python3
"""
DQIII8 — Quick Enricher v4 Benchmark

Lightweight A/B test: 5 tasks (1 per domain) × 3 runs × 2 modes = 30 LLM calls.
Compares DQ ON (v4 enricher) vs DQ OFF (no enrichment).
Stores results in knowledge_benchmark_results for comparison with v2 baseline.

Usage:
    python3 bin/tools/benchmark_v4_quick.py
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

DQIII8_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = DQIII8_ROOT / "database" / "jarvis_metrics.db"
WRAPPER = DQIII8_ROOT / "bin" / "core" / "openrouter_wrapper.py"

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Load .env
_env_path = DQIII8_ROOT / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        if "=" in _line and not _line.startswith("#"):
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

# 5 tasks — 1 per domain (subset of benchmark_dq.py)
TASKS = [
    {
        "id": "FS01",
        "domain": "formal_sciences",
        "prompt": "Explain the Kelly Criterion for optimal bet sizing. Include the mathematical formula, derive it from first principles, and give a practical example with a coinflip that has 60% win probability and 2:1 payout.",
        "keywords": ["kelly", "f*", "bankroll", "edge", "odds"],
    },
    {
        "id": "NS01",
        "domain": "natural_sciences",
        "prompt": "Explain the Katch-McArdle BMR formula. How does it differ from Mifflin-St Jeor? Calculate BMR for a 75kg male with 15% body fat using both formulas.",
        "keywords": ["lean mass", "BMR", "kcal", "body fat", "metabolic"],
    },
    {
        "id": "SS01",
        "domain": "social_sciences",
        "prompt": "Explain the WACC formula for corporate valuation. Break down each component (cost of equity via CAPM, cost of debt, tax shield) and calculate WACC for a company with 60% equity, 40% debt, beta=1.2, risk-free=4%, market premium=6%, pre-tax cost of debt=5%, tax rate=25%.",
        "keywords": ["WACC", "CAPM", "beta", "cost of equity", "tax shield"],
    },
    {
        "id": "AS01",
        "domain": "applied_sciences",
        "prompt": "Explain Python's asyncio event loop architecture. How do coroutines differ from threads? Show a practical example of concurrent HTTP requests using aiohttp with proper error handling and connection pooling.",
        "keywords": ["event loop", "coroutine", "await", "aiohttp", "concurrent"],
    },
    {
        "id": "HA01",
        "domain": "humanities_arts",
        "prompt": "Analyze the narrative structure techniques in Christopher Nolan's films. How does he use non-linear storytelling, and what psychological effects does this create on the viewer? Compare at least 3 of his films.",
        "keywords": ["non-linear", "narrative", "temporal", "Memento", "Inception"],
    },
]

RUNS_PER_TASK = 3


def call_model(prompt: str, use_dq: bool) -> str:
    cmd = ["python3", str(WRAPPER)]
    if not use_dq:
        cmd.append("--no-enrich")
    cmd.append(prompt)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120, cwd=str(DQIII8_ROOT)
        )
        return result.stdout.strip()[:3000]
    except subprocess.TimeoutExpired:
        return "[TIMEOUT]"
    except Exception as exc:
        return f"[ERROR: {exc}]"


def score_response(response: str, keywords: list[str]) -> float:
    """Simple keyword-overlap scoring (0-10 scale)."""
    if not response or response.startswith("["):
        return 0.0
    text_lower = response.lower()
    hits = sum(1 for kw in keywords if kw.lower() in text_lower)
    base = (hits / max(len(keywords), 1)) * 7.0  # 0-7 for keywords
    length_bonus = min(len(response) / 500, 3.0)  # 0-3 for substance
    return round(min(base + length_bonus, 10.0), 2)


def save_result(
    task: dict, run: int, dq_enabled: bool, score: float, response_len: int
) -> None:
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        """INSERT INTO knowledge_benchmark_results
           (task_id, task_text, task_domain, config, model, dq_enabled,
            overall_score, tokens_response, judge_model)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            task["id"],
            task["prompt"][:200],
            task["domain"],
            "v4_quick",
            "groq_llama-3.3-70b",
            1 if dq_enabled else 0,
            score,
            response_len,
            "keyword_overlap",
        ),
    )
    conn.commit()
    conn.close()


def main() -> None:
    print(f"\n{'='*60}")
    print(f"  Enricher v4 Quick Benchmark")
    print(
        f"  {len(TASKS)} tasks × {RUNS_PER_TASK} runs × 2 modes = {len(TASKS)*RUNS_PER_TASK*2} calls"
    )
    print(f"  DQ_ENRICHER_VERSION = {os.environ.get('DQ_ENRICHER_VERSION', 'v4')}")
    print(f"{'='*60}\n")

    all_results: list[dict] = []

    for t_idx, task in enumerate(TASKS):
        print(f"\n--- Task {t_idx+1}/{len(TASKS)}: {task['id']} ({task['domain']}) ---")

        for run in range(1, RUNS_PER_TASK + 1):
            # DQ OFF
            resp_off = call_model(task["prompt"], use_dq=False)
            score_off = score_response(resp_off, task["keywords"])
            save_result(task, run, False, score_off, len(resp_off))

            # DQ ON (v4)
            resp_on = call_model(task["prompt"], use_dq=True)
            score_on = score_response(resp_on, task["keywords"])
            save_result(task, run, True, score_on, len(resp_on))

            print(
                f"  Run {run}: OFF={score_off:.1f} ON={score_on:.1f} "
                f"(delta={score_on - score_off:+.1f})"
            )
            all_results.append(
                {
                    "task": task["id"],
                    "domain": task["domain"],
                    "run": run,
                    "off": score_off,
                    "on": score_on,
                }
            )
            time.sleep(2)

    # Summary
    print(f"\n{'='*60}")
    print("  RESULTS BY DOMAIN")
    print(f"{'='*60}")

    conn = sqlite3.connect(str(DB_PATH))

    # v4 results (this run)
    print("\n  === Enricher v4 (this run, config=v4_quick) ===")
    v4_rows = conn.execute("""SELECT task_domain,
              ROUND(AVG(CASE WHEN dq_enabled=1 THEN overall_score END), 2) as on_score,
              ROUND(AVG(CASE WHEN dq_enabled=0 THEN overall_score END), 2) as off_score,
              ROUND(AVG(CASE WHEN dq_enabled=1 THEN overall_score END) -
                    AVG(CASE WHEN dq_enabled=0 THEN overall_score END), 2) as uplift,
              COUNT(*) as n
           FROM knowledge_benchmark_results
           WHERE config = 'v4_quick'
           GROUP BY task_domain ORDER BY task_domain""").fetchall()
    print(f"  {'Domain':20s} {'ON':>6s} {'OFF':>6s} {'Uplift':>8s} {'N':>4s}")
    print(f"  {'-'*44}")
    for domain, on_s, off_s, uplift, n in v4_rows:
        marker = "+" if (uplift or 0) >= 0 else "!!"
        print(f"  {domain:20s} {on_s:6.2f} {off_s:6.2f} {uplift:+8.2f} {n:4d} {marker}")

    # v2 baseline comparison
    print("\n  === Enricher v2 (historical baseline) ===")
    v2_rows = conn.execute("""SELECT task_domain,
              ROUND(AVG(CASE WHEN dq_enabled=1 THEN overall_score END), 2) as on_score,
              ROUND(AVG(CASE WHEN dq_enabled=0 THEN overall_score END), 2) as off_score,
              ROUND(AVG(CASE WHEN dq_enabled=1 THEN overall_score END) -
                    AVG(CASE WHEN dq_enabled=0 THEN overall_score END), 2) as uplift,
              COUNT(*) as n
           FROM knowledge_benchmark_results
           WHERE config != 'v4_quick'
           GROUP BY task_domain ORDER BY task_domain""").fetchall()
    print(f"  {'Domain':20s} {'ON':>6s} {'OFF':>6s} {'Uplift':>8s} {'N':>4s}")
    print(f"  {'-'*44}")
    for domain, on_s, off_s, uplift, n in v2_rows:
        print(f"  {domain:20s} {on_s:6.2f} {off_s:6.2f} {uplift:+8.2f} {n:4d}")

    conn.close()
    print()


if __name__ == "__main__":
    main()
