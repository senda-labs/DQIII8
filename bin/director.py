#!/usr/bin/env python3
"""
DQIII8 — Director Central v3

Real intent parsing: LLM (tier2) + instincts DB + model_router.
Extends the static keyword routing from CLAUDE.md to semantic analysis.

Usage:
    python3 bin/director.py "analyze Apple WACC and generate an executive report"
    python3 bin/director.py --json "backtesting momentum strategy BTC 3 years"
    python3 bin/director.py --quiet "write chapter 3 of the novel"
    echo "request" | python3 bin/director.py

Importable:
    from director import analyze_intent
    plan = analyze_intent("backtesting momentum BTC")
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

JARVIS_ROOT = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB_PATH = JARVIS_ROOT / "database" / "jarvis_metrics.db"
WRAPPER = JARVIS_ROOT / "bin" / "openrouter_wrapper.py"

# ── Static mapping tables ─────────────────────────────────────────────────────

TASK_AGENT_MAP: dict[str, str] = {
    "code": "python-specialist",
    "analysis": "data-analyst",
    "finance": "finance-analyst",
    "writing": "creative-writer",
    "research": "research-analyst",
    "pipeline": "content-automator",
    "trading": "quant-analyst",
    "mixed": "orchestrator",
}

TASK_TIER_MAP: dict[str, int] = {
    "code": 1,
    "pipeline": 1,
    "research": 2,
    "analysis": 3,
    "finance": 3,
    "trading": 3,
    "writing": 3,
    "mixed": 3,
}

# Keywords → task_type for fast-path (instincts + keyword fallback)
KEYWORD_TASK_TYPE: dict[str, str] = {
    "backtesting": "trading",
    "backtest": "trading",
    "momentum": "trading",
    "trading": "trading",
    "strategy": "trading",
    "binance": "trading",
    "sharpe": "trading",
    "garch": "trading",
    "arbitrage": "trading",
    "wacc": "finance",
    "dcf": "finance",
    "valoraci": "finance",
    "financi": "finance",
    "cost of capital": "finance",
    "balance": "analysis",
    "novel": "writing",
    "chapter": "writing",
    "narrativ": "writing",
    "dialogue": "writing",
    "scene": "writing",
    "research": "research",
    "investiga": "research",
    "video": "pipeline",
    "subtitles": "pipeline",
    "tts": "pipeline",
    "elevenlabs": "pipeline",
    "reels": "pipeline",
    "python": "code",
    "refactor": "code",
    "debug": "code",
    "script": "code",
    "pytest": "code",
    "function": "code",
}

OUTPUT_FORMAT_KEYWORDS: dict[str, str] = {
    "report": "report",
    "email": "email",
    "pdf": "pdf",
    "script": "script",
    "code": "code",
    "markdown": "markdown",
}

# ── Prompt LLM ────────────────────────────────────────────────────────────────

_ANALYSIS_PROMPT = """\
You are a task classifier for DQIII8, an AI agent system.

Analyze the user request and produce ONLY a valid JSON object
(no additional text, no markdown blocks, no explanations).

Required JSON schema:
{{
  "task_type": "<code|analysis|finance|writing|research|pipeline|trading|mixed>",
  "subtasks": [
    {{
      "description": "<concise subtask description>",
      "agent": "<python-specialist|data-analyst|finance-analyst|quant-analyst|creative-writer|research-analyst|content-automator|orchestrator|code-reviewer|git-specialist>",
      "parallel": <true|false>,
      "depends_on": []
    }}
  ],
  "output_format": "<markdown|pdf|email|script|code|report>",
  "complexity": "<simple|medium|complex>",
  "recommended_tier": <1|2|3>
}}

Agent and tier assignment rules:
- task_type=code      → agent=python-specialist,  tier=1
- task_type=pipeline  → agent=content-automator,  tier=1
- task_type=research  → agent=research-analyst,   tier=2
- task_type=analysis  → agent=data-analyst,        tier=3  (pandas, matplotlib, statistics)
- task_type=finance   → agent=finance-analyst,     tier=3  (WACC, DCF, valuation, ratios)
- task_type=trading   → agent=quant-analyst,       tier=3  (backtesting, VaR, GARCH)
- task_type=writing   → agent=creative-writer,     tier=3  (novel, narrative, dialogue)
- task_type=mixed     → multiple subtasks with depends_on, tier=3

For mixed tasks, split into ordered subtasks. The first subtask
with parallel=false and depends_on=[] is the entry point. The following
can be parallel if they do not depend on each other.

User request: "{request}"

Respond ONLY with the JSON. No markdown, no additional text."""


# ── Instincts DB ──────────────────────────────────────────────────────────────


def _query_instincts_fast_path(user_request: str) -> tuple[str | None, float]:
    """
    Searches instincts with confidence > 0.7 whose keyword appears in the request.
    If there is a match → returns (task_type, confidence) to skip the LLM call.
    Returns (None, 0.0) if there is no sufficient match.
    """
    if not DB_PATH.exists():
        return None, 0.0

    lowered = user_request.lower()
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=2)
        rows = conn.execute(
            "SELECT keyword, confidence FROM instincts "
            "WHERE confidence > 0.7 ORDER BY confidence DESC LIMIT 100"
        ).fetchall()
        conn.close()
    except Exception:
        return None, 0.0

    for keyword, confidence in rows:
        kw_lower = keyword.lower()
        if kw_lower in lowered:
            for prefix, task_type in KEYWORD_TASK_TYPE.items():
                if prefix in kw_lower:
                    return task_type, float(confidence)

    return None, 0.0


# ── model_router integration ──────────────────────────────────────────────────


def _get_model_for_task(task_type: str) -> tuple[str, float]:
    """
    Queries model_router.get_recommendation() for the given task_type.
    Returns (model_name, score). Falls back to defaults if import fails.
    """
    bin_dir = str(JARVIS_ROOT / "bin")
    if bin_dir not in sys.path:
        sys.path.insert(0, bin_dir)
    try:
        from openrouter_wrapper import get_recommendation  # type: ignore

        model, score, _ = get_recommendation(task_type)
        return model, score
    except Exception:
        _defaults: dict[str, str] = {
            "code": "qwen2.5-coder:7b",
            "pipeline": "qwen2.5-coder:7b",
            "research": "llama-3.3-70b-versatile",
            "analysis": "claude-sonnet-4-6",
            "trading": "claude-sonnet-4-6",
            "writing": "claude-sonnet-4-6",
            "mixed": "claude-sonnet-4-6",
        }
        return _defaults.get(task_type, "claude-sonnet-4-6"), 0.5


# ── LLM call via openrouter_wrapper ──────────────────────────────────────────


def _call_llm_for_intent(user_request: str) -> dict | None:
    """
    Calls the tier2 model (research-analyst) via openrouter_wrapper for
    intent analysis. Captures stdout (JSON response), ignores stderr.
    Returns the parsed dict, or None if the call or parse fails.
    """
    prompt = _ANALYSIS_PROMPT.format(request=user_request.replace('"', '\\"'))
    try:
        result = subprocess.run(
            [sys.executable, str(WRAPPER), "--agent", "research-analyst", prompt],
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ},
        )
        raw = result.stdout.strip()
        if not raw:
            return None
        # Extract first JSON block from output (the LLM may add extra text)
        json_match = re.search(r"\{[\s\S]*\}", raw)
        if not json_match:
            return None
        return json.loads(json_match.group())
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
        return None


# ── Fallback: keyword-only analysis (no LLM) ─────────────────────────────────


def _keyword_fallback(user_request: str) -> dict:
    """
    Analysis without LLM: static keywords + mapping tables.
    Used when the LLM is unavailable or times out.
    """
    lowered = user_request.lower()

    task_type = "mixed"
    for kw, tt in KEYWORD_TASK_TYPE.items():
        if kw in lowered:
            task_type = tt
            break

    output_format = "markdown"
    for kw, fmt in OUTPUT_FORMAT_KEYWORDS.items():
        if kw in lowered:
            output_format = fmt
            break

    word_count = len(user_request.split())
    if word_count < 8:
        complexity = "simple"
    elif word_count < 20:
        complexity = "medium"
    else:
        complexity = "complex"

    agent = TASK_AGENT_MAP.get(task_type, "orchestrator")
    tier = TASK_TIER_MAP.get(task_type, 3)

    return {
        "task_type": task_type,
        "subtasks": [
            {
                "description": user_request,
                "agent": agent,
                "parallel": False,
                "depends_on": [],
            }
        ],
        "output_format": output_format,
        "complexity": complexity,
        "recommended_tier": tier,
    }


# ── Main function ─────────────────────────────────────────────────────────────


def analyze_intent(user_request: str, verbose: bool = True) -> dict:
    """
    Analyzes the intent of a request and returns an execution plan.

    Priority:
      1. Instincts DB (confidence > 0.7) → fast path without LLM
      2. LLM via openrouter_wrapper (tier2, free)
      3. Static keyword fallback

    Enriches each subtask with 'recommended_model' and 'model_score'
    via model_router.get_recommendation().

    Args:
        user_request: User request in natural language.
        verbose: If True, prints status to stderr.

    Returns:
        dict with keys: task_type, subtasks, output_format, complexity,
        recommended_tier, _source.
    """

    def _log(msg: str) -> None:
        if verbose:
            print(f"[director] {msg}", file=sys.stderr)

    plan: dict | None = None
    source = "llm"

    # Step 1: Query high-confidence instincts
    instinct_task_type, instinct_confidence = _query_instincts_fast_path(user_request)

    if instinct_task_type:
        _log(
            f"instinct match: {instinct_task_type} "
            f"(conf={instinct_confidence:.2f}) — skipping LLM"
        )
        source = f"instinct:{instinct_confidence:.2f}"
        agent = TASK_AGENT_MAP.get(instinct_task_type, "orchestrator")
        tier = TASK_TIER_MAP.get(instinct_task_type, 3)
        plan = {
            "task_type": instinct_task_type,
            "subtasks": [
                {
                    "description": user_request,
                    "agent": agent,
                    "parallel": False,
                    "depends_on": [],
                }
            ],
            "output_format": "report",
            "complexity": "medium",
            "recommended_tier": tier,
        }
    else:
        # Step 2: LLM via openrouter_wrapper (tier2, free)
        _log("querying LLM for intent analysis...")
        plan = _call_llm_for_intent(user_request)

        if plan is None:
            # Single retry after 2 seconds
            _log("retrying LLM after failure...")
            import time as _time

            _time.sleep(2)
            plan = _call_llm_for_intent(user_request)

        if plan is None:
            # Step 3: Keyword fallback
            _log("LLM unavailable — using keyword fallback")
            source = "keyword_fallback"
            plan = _keyword_fallback(user_request)

    # Validate required plan fields (LLM output may be incomplete)
    plan.setdefault("task_type", "mixed")
    plan.setdefault("subtasks", [])
    plan.setdefault("output_format", "markdown")
    plan.setdefault("complexity", "medium")
    plan.setdefault("recommended_tier", 3)

    if not plan["subtasks"]:
        # LLM returned empty plan — rebuild from task_type
        agent = TASK_AGENT_MAP.get(plan["task_type"], "orchestrator")
        plan["subtasks"] = [
            {"description": user_request, "agent": agent, "parallel": False, "depends_on": []}
        ]

    # Step 4: Enrich subtasks with model_router
    task_type = plan["task_type"]
    for subtask in plan["subtasks"]:
        subtask.setdefault("parallel", False)
        subtask.setdefault("depends_on", [])

        # Resolve agent task_type for model_router lookup
        agent = subtask.get("agent", "")
        agent_task_type_map = {
            "quant-analyst": "trading",
            "data-analyst": "analysis",
            "creative-writer": "writing",
            "python-specialist": "code",
            "git-specialist": "code",
            "research-analyst": "research",
            "content-automator": "pipeline",
        }
        st_type = agent_task_type_map.get(agent, task_type)

        model, score = _get_model_for_task(st_type)
        subtask["recommended_model"] = model
        subtask["model_score"] = score

    plan["_source"] = source
    return plan


# ── CLI ───────────────────────────────────────────────────────────────────────


def _print_human(plan: dict) -> None:
    """Human-readable format of the plan."""
    tt = plan.get("task_type", "?")
    tier = plan.get("recommended_tier", "?")
    complexity = plan.get("complexity", "?")
    fmt = plan.get("output_format", "?")
    source = plan.get("_source", "?")
    subtasks = plan.get("subtasks", [])

    print()
    print("[DIRECTOR v3] Intent Analysis")
    print(f"  task_type       : {tt}")
    print(f"  complexity      : {complexity}")
    print(f"  output_format   : {fmt}")
    print(f"  recommended_tier: {tier}")
    print(f"  source          : {source}")
    print(f"  subtasks        : {len(subtasks)}")

    for i, st in enumerate(subtasks):
        parallel = "parallel" if st.get("parallel") else "sequential"
        deps = st.get("depends_on", [])
        dep_str = f"  depends_on={deps}" if deps else ""
        model = st.get("recommended_model", "?")
        score = st.get("model_score", 0.0)
        desc = st.get("description", "")[:72]
        print(f"\n  [{i}] agent={st.get('agent', '?')}  {parallel}{dep_str}")
        print(f"       desc  : {desc}")
        print(f"       model : {model}  (score={score:.2f})")
    print()


def main() -> None:
    argv = sys.argv[1:]
    as_json = "--json" in argv
    quiet = "--quiet" in argv
    argv = [a for a in argv if not a.startswith("--")]

    if argv:
        request = " ".join(argv)
    elif not sys.stdin.isatty():
        request = sys.stdin.read().strip()
    else:
        print(
            'Usage: python3 bin/director.py [--json|--quiet] "<request>"',
            file=sys.stderr,
        )
        sys.exit(1)

    if not request:
        print("[director] Error: empty request.", file=sys.stderr)
        sys.exit(1)

    plan = analyze_intent(request, verbose=not quiet)

    if quiet:
        # Compact line for integration with other scripts
        agent = plan["subtasks"][0]["agent"] if plan.get("subtasks") else "?"
        print(
            f"task_type={plan.get('task_type')} "
            f"agent={agent} "
            f"tier={plan.get('recommended_tier')}"
        )
    else:
        if not as_json:
            _print_human(plan)
        print(json.dumps(plan, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
