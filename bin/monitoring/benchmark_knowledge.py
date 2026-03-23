#!/usr/bin/env python3
"""
DQ Knowledge Benchmark — measures uplift of knowledge-enriched prompts.

Usage:
  python3 bin/monitoring/benchmark_knowledge.py --run          # Run all 120 evaluations
  python3 bin/monitoring/benchmark_knowledge.py --run --task 5  # Run task 5 only (6 configs)
  python3 bin/monitoring/benchmark_knowledge.py --report        # Generate comparison report
  python3 bin/monitoring/benchmark_knowledge.py --export csv    # Export results to CSV
"""

import sys
import os
import json
import time
import argparse
import csv
from pathlib import Path

JARVIS = Path(os.environ.get("DQIII8_ROOT", "/root/jarvis"))
for subdir in ["core", "agents", "monitoring", "tools", "ui", ""]:
    p = str(JARVIS / "bin" / subdir) if subdir else str(JARVIS / "bin")
    if p not in sys.path:
        sys.path.insert(0, p)

from db import get_db

TASKS_FILE = JARVIS / "tasks" / "benchmark_tasks.json"

CONFIGS = [
    {"name": "A", "model": "qwen2.5-coder:7b", "provider": "ollama", "dq": False},
    {"name": "B", "model": "qwen2.5-coder:7b", "provider": "ollama", "dq": True},
    {"name": "C", "model": "llama-3.3-70b-versatile", "provider": "groq", "dq": False},
    {"name": "D", "model": "llama-3.3-70b-versatile", "provider": "groq", "dq": True},
    {"name": "E", "model": "claude-sonnet-4-6", "provider": "anthropic", "dq": False},
    {"name": "F", "model": "claude-sonnet-4-6", "provider": "anthropic", "dq": True},
]


def load_tasks():
    with open(TASKS_FILE) as f:
        return json.load(f)


def run_task(task, config):
    """Execute a single task with a specific config and measure all variables."""
    prompt = task["text"]
    knowledge_used = ""

    if config["dq"]:
        try:
            from intent_amplifier import amplify

            result = amplify(prompt)
            prompt = result["amplified"]
            knowledge_used = json.dumps(result.get("niche", []))
        except Exception as e:
            print(f"  Warning: Amplification failed: {e}")

    start = time.time()

    if config["provider"] == "ollama":
        response = _run_ollama(prompt, config["model"])
    elif config["provider"] == "groq":
        response = _run_groq(prompt, config["model"])
    elif config["provider"] == "anthropic":
        response = _run_anthropic(prompt, config["model"])
    else:
        response = {"text": "", "tokens_prompt": 0, "tokens_response": 0}

    elapsed = round(time.time() - start, 2)

    return {
        "task_id": task["id"],
        "task_text": task["text"],
        "task_domain": task["domain"],
        "config": config["name"],
        "model": config["model"],
        "dq_enabled": config["dq"],
        "knowledge_injected": knowledge_used,
        "response_text": response.get("text", ""),
        "tokens_prompt": response.get("tokens_prompt", 0),
        "tokens_response": response.get("tokens_response", 0),
        "tokens_total": response.get("tokens_prompt", 0)
        + response.get("tokens_response", 0),
        "time_seconds": elapsed,
        "messages_needed": 1,
        "cost_usd": _estimate_cost(config, response),
    }


def _run_ollama(prompt, model):
    try:
        import requests

        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 400},
            },
            timeout=120,
        )
        data = resp.json()
        return {
            "text": data.get("response", ""),
            "tokens_prompt": data.get("prompt_eval_count", 0),
            "tokens_response": data.get("eval_count", 0),
        }
    except Exception as e:
        return {
            "text": f"[Ollama error: {e}]",
            "tokens_prompt": 0,
            "tokens_response": 0,
        }


def _run_groq(prompt, model):
    try:
        from groq import Groq

        client = Groq(api_key=os.environ.get("GROQ_API_KEY", ""))
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
        )
        return {
            "text": resp.choices[0].message.content,
            "tokens_prompt": resp.usage.prompt_tokens,
            "tokens_response": resp.usage.completion_tokens,
        }
    except Exception as e:
        return {"text": f"[Groq error: {e}]", "tokens_prompt": 0, "tokens_response": 0}


def _run_anthropic(prompt, model):
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        resp = client.messages.create(
            model=model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        return {
            "text": resp.content[0].text,
            "tokens_prompt": resp.usage.input_tokens,
            "tokens_response": resp.usage.output_tokens,
        }
    except Exception as e:
        return {
            "text": f"[Anthropic error: {e}]",
            "tokens_prompt": 0,
            "tokens_response": 0,
        }


def _estimate_cost(config, response):
    tp = response.get("tokens_prompt", 0)
    tr = response.get("tokens_response", 0)
    if config["provider"] == "ollama":
        return 0.0
    elif config["provider"] == "groq":
        return 0.0
    elif config["provider"] == "anthropic":
        # claude-sonnet-4-6: $3/MTok input, $15/MTok output
        return round((tp * 3 + tr * 15) / 1_000_000, 6)
    return 0.0


def evaluate_with_judge(task, response_text):
    """Use Groq (free) as LLM-as-judge to score response quality 0-10."""
    judge_prompt = f"""You are evaluating an AI response. Rate it strictly 0-10 on three dimensions.

TASK: {task['text']}

RESPONSE TO EVALUATE:
{response_text[:3000]}

Rate STRICTLY (0=completely wrong, 5=partially correct, 10=perfect):
1. ACCURACY (0-10): Are facts, numbers, and formulas correct?
2. COMPLETENESS (0-10): Does it cover all aspects of the task?
3. PRECISION (0-10): Are specific values exact (not vague or invented)?

Count HALLUCINATIONS: facts stated confidently that are wrong or invented.

Respond ONLY with this JSON (no other text):
{{"accuracy": X, "completeness": X, "precision": X, "hallucinations": N, "errors": "brief list or none"}}"""

    try:
        from groq import Groq

        client = Groq(api_key=os.environ.get("GROQ_API_KEY", ""))
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": judge_prompt}],
            max_tokens=200,
            temperature=0.0,
        )
        text = resp.choices[0].message.content.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        print(f"  Warning: Judge failed: {e}")
        return {
            "accuracy": 0,
            "completeness": 0,
            "precision": 0,
            "hallucinations": 0,
            "errors": f"judge error: {e}",
        }


def save_result(result, eval_data):
    overall = round(
        (
            eval_data.get("accuracy", 0)
            + eval_data.get("completeness", 0)
            + eval_data.get("precision", 0)
        )
        / 3,
        2,
    )
    tier = (
        "A"
        if result["model"].startswith("qwen")
        or "ollama" in result.get("knowledge_injected", "")
        else ("B" if result["model"].startswith("llama") else "C")
    )
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO knowledge_benchmark_results
            (task_id, task_text, task_domain, config, model, dq_enabled, knowledge_injected,
             accuracy_score, completeness_score, precision_score, overall_score,
             tokens_prompt, tokens_response, tokens_total, time_seconds, messages_needed,
             cost_usd, tier_used, escalation_needed, hallucination_count, factual_errors,
             judge_model, human_verified)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                result["task_id"],
                result["task_text"],
                result["task_domain"],
                result["config"],
                result["model"],
                int(result["dq_enabled"]),
                result["knowledge_injected"],
                eval_data.get("accuracy", 0),
                eval_data.get("completeness", 0),
                eval_data.get("precision", 0),
                overall,
                result["tokens_prompt"],
                result["tokens_response"],
                result["tokens_total"],
                result["time_seconds"],
                result["messages_needed"],
                result["cost_usd"],
                tier,
                False,
                eval_data.get("hallucinations", 0),
                eval_data.get("errors", ""),
                "llama-3.3-70b-versatile",
                False,
            ),
        )


def generate_report():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT COUNT(*) FROM knowledge_benchmark_results"
        ).fetchone()
        if not rows or rows[0] == 0:
            print("No benchmark results yet. Run with --run first.")
            return

        print("\n" + "=" * 72)
        print("DQ KNOWLEDGE BENCHMARK REPORT")
        print("=" * 72)

        summary = conn.execute(
            "SELECT * FROM knowledge_benchmark_summary ORDER BY model, dq_enabled"
        ).fetchall()
        if summary:
            print(
                f"\n{'Config':<8} {'Model':<26} {'DQ':<4} {'Score':<7} {'Tokens':<8} {'Time':<7} {'Halluc':<8} {'N'}"
            )
            print("-" * 72)
            for r in summary:
                dq_str = "ON " if r[2] else "OFF"
                print(
                    f"{r[0]:<8} {r[1]:<26} {dq_str:<4} {r[4]:<7} {r[5]:<8.0f} {r[6]:<7.1f} {r[9]:<8.1f} {r[10]}"
                )

        uplift = conn.execute(
            "SELECT * FROM knowledge_benchmark_dq_uplift ORDER BY model"
        ).fetchall()
        if uplift:
            print(
                f"\n{'Model':<26} {'Domain':<22} {'Score ↑':<9} {'Tokens ↓':<11} {'Halluc ↓'}"
            )
            print("-" * 72)
            for r in uplift:
                print(
                    f"{r[0]:<26} {r[1]:<22} {r[2]:+.2f}     {r[3]:+.0f}        {r[5]:+.1f}"
                )

        print("\n" + "=" * 72)


def export_csv(filepath="tasks/knowledge_benchmark_results.csv"):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM knowledge_benchmark_results ORDER BY id"
        ).fetchall()
        cols = [
            d[0]
            for d in conn.execute(
                "PRAGMA table_info(knowledge_benchmark_results)"
            ).fetchall()
        ]

    path = JARVIS / filepath
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(cols)
        writer.writerows(rows)
    print(f"Exported {len(rows)} rows to {path}")


def main():
    parser = argparse.ArgumentParser(description="DQ Knowledge Benchmark")
    parser.add_argument("--run", action="store_true", help="Run benchmark evaluations")
    parser.add_argument("--task", type=int, help="Run specific task ID only")
    parser.add_argument("--config", type=str, help="Run specific config only (A-F)")
    parser.add_argument(
        "--report", action="store_true", help="Generate report from existing results"
    )
    parser.add_argument("--export", type=str, help="Export results (csv)")
    args = parser.parse_args()

    if args.export:
        export_csv()
        return

    if args.report:
        generate_report()
        return

    if args.run:
        tasks = load_tasks()
        if args.task:
            tasks = [t for t in tasks if t["id"] == args.task]

        configs = CONFIGS
        if args.config:
            configs = [c for c in CONFIGS if c["name"] == args.config.upper()]

        total = len(tasks) * len(configs)
        done = 0

        for task in tasks:
            for config in configs:
                done += 1
                print(
                    f"[{done}/{total}] Task {task['id']} | Config {config['name']} "
                    f"({config['model']}, DQ={'ON' if config['dq'] else 'OFF'})",
                    flush=True,
                )

                if config["provider"] == "anthropic" and not os.environ.get(
                    "ANTHROPIC_API_KEY"
                ):
                    print("  Skipped (no ANTHROPIC_API_KEY)")
                    continue

                if config["provider"] == "groq" and not os.environ.get("GROQ_API_KEY"):
                    print("  Skipped (no GROQ_API_KEY)")
                    continue

                result = run_task(task, config)
                eval_data = evaluate_with_judge(task, result["response_text"])
                save_result(result, eval_data)

                score = round(
                    (
                        eval_data.get("accuracy", 0)
                        + eval_data.get("completeness", 0)
                        + eval_data.get("precision", 0)
                    )
                    / 3,
                    1,
                )
                print(
                    f"  Score: {score}/10 | Tokens: {result['tokens_total']} | "
                    f"Time: {result['time_seconds']}s | Halluc: {eval_data.get('hallucinations', 0)}",
                    flush=True,
                )

        print(f"\nBenchmark complete: {done} evaluations")
        generate_report()
        return

    parser.print_help()


if __name__ == "__main__":
    main()
