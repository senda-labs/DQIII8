#!/usr/bin/env python3
"""
Benchmark: Groq vs Claude Haiku 4.5 vs Claude Sonnet 4.6
Compares script quality, latency, and word count for viral content generation.

Usage: python3 /root/jarvis/bin/script_benchmark.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, "/root/content-automation-faceless")
os.chdir("/root/content-automation-faceless")

from dotenv import load_dotenv

load_dotenv("config/.env", override=True)

# ── Config ─────────────────────────────────────────────────────────────────

PROMPT_TOPIC = "The Black Death killed 50% of Europe in 5 years. Nobody understood why."
DURATION = 30
LANG = "en"

SYSTEM_PROMPT = (
    "You are a viral short-form video script generator.\n"
    "VIRAL HOOK RULES (non-negotiable):\n"
    "1. First sentence = shocking stat or paradox. Max 10 words.\n"
    "2. Max 10 words per sentence. Hard limit.\n"
    "3. STACCATO format: short declarative sentences only.\n"
    "4. Output ONLY the script text. No headers, no labels."
)

USER_PROMPT = (
    f"Topic: {PROMPT_TOPIC}\n"
    f"Duration: {DURATION}s (~75 words)\n"
    f"Language: {LANG}\n"
    f"Mode: viral_hook"
)


# ── Generators ─────────────────────────────────────────────────────────────


def gen_groq() -> dict:
    from backend.services.script_service import ScriptService

    svc = ScriptService()
    t0 = time.time()
    result = svc.generate_with_quality_control(
        PROMPT_TOPIC, DURATION, mode="viral_hook", language=LANG
    )
    return {
        "text": result["full_script"],
        "latency": time.time() - t0,
        "word_count": result["word_count"],
        "score": result["quality_score"]["average"],
    }


def _parse_cli_output(raw: str) -> str:
    """Extract script text from claude CLI JSON output. Handles warnings before JSON."""
    raw = raw.strip()
    if not raw:
        return ""
    # Try direct JSON parse (outer CLI wrapper)
    try:
        outer = json.loads(raw)
        return outer.get("result", raw).strip()
    except json.JSONDecodeError:
        pass
    # Regex: find first {...} block (handles prefixed warnings/noise)
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            outer = json.loads(m.group(0))
            return outer.get("result", raw).strip()
        except json.JSONDecodeError:
            pass
    return raw


def gen_claude_headless(model: str) -> dict:
    prompt = f"{SYSTEM_PROMPT}\n\n{USER_PROMPT}"
    t0 = time.time()
    clean_env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json", "--model", model],
        capture_output=True,
        text=True,
        timeout=120,
        env=clean_env,
    )
    latency = time.time() - t0
    if result.returncode != 0:
        raise RuntimeError(f"claude CLI error: {result.stderr[:200]}")
    text = _parse_cli_output(result.stdout)
    words = text.split()
    return {
        "text": text,
        "latency": latency,
        "word_count": len(words),
        "score": None,  # No local scorer for Claude outputs in benchmark
    }


# ── Benchmark Runner ────────────────────────────────────────────────────────

PROVIDERS = [
    ("Groq Llama-3.3-70B (current)", lambda: gen_groq()),
    (
        "Claude Haiku 4.5 (claude-haiku-4-5-20251001)",
        lambda: gen_claude_headless("claude-haiku-4-5-20251001"),
    ),
    ("Claude Sonnet 4.6 (claude-sonnet-4-6)", lambda: gen_claude_headless("claude-sonnet-4-6")),
]

if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"SCRIPT BENCHMARK — {LANG.upper()} | {DURATION}s | viral_hook")
    print(f"Topic: {PROMPT_TOPIC[:60]}...")
    print(f"{'='*60}")

    results: dict[str, dict] = {}

    for name, fn in PROVIDERS:
        print(f"\n--- {name} ---")
        try:
            r = fn()
            results[name] = r
            score_str = f"{r['score']:.2f}" if r["score"] is not None else "N/A (no local scorer)"
            print(f"  Latency:    {r['latency']:.1f}s")
            print(f"  Words:      {r['word_count']}")
            print(f"  Score:      {score_str}")
            print(f"  Hook:       {r['text'][:120]}...")
        except Exception as e:
            print(f"  ERROR: {e}")
            results[name] = {"error": str(e), "latency": 0, "word_count": 0, "score": 0}

    print(f"\n{'='*60}")
    print("WINNER")
    print(f"{'='*60}")
    valid = {k: v for k, v in results.items() if "error" not in v}
    if valid:
        # Sort: score desc (None treated as 7.0 baseline), then word_count desc, then latency asc
        def rank(item: tuple) -> tuple:
            v = item[1]
            return (v.get("score") or 7.0, v["word_count"], -v["latency"])

        ranked = sorted(valid.items(), key=rank, reverse=True)
        winner_name, winner = ranked[0]
        print(f"  🏆 {winner_name}")
        print(f"     Words: {winner['word_count']} | Latency: {winner['latency']:.1f}s")
        print(f"\nFull ranking:")
        for i, (n, v) in enumerate(ranked, 1):
            score_str = f"{v['score']:.2f}" if v["score"] is not None else "N/A"
            print(
                f"  {i}. {n}: score={score_str}, words={v['word_count']}, latency={v['latency']:.1f}s"
            )
    else:
        print("  ❌ All providers failed.")
