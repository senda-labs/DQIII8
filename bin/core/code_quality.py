#!/usr/bin/env python3
"""
DQIII8 — Code Quality Pipeline (MetaGPT-pattern, native)

MetaGPT is not installable on Python 3.12 (dependency conflicts), so this
module implements the *pattern* natively on top of the dqiii8 routing layer
and a LangGraph ``StateGraph``.

Pipeline (richer than vanilla MetaGPT):

    START
      └─► optimization_analysis   (NIM Mistral 675B — cheap pre-review of the spec)
            └─► engineer_cityblock (NIM DeepSeek V4 Flash — generate ONE block)
                  └─► attack_block (sandbox execution + adversarial check)
                        └─► haiku_bombardment (30s ingest → 100 adversarial Qs)
                              └─► reviewer (Opus — ONLY if gaps over threshold)
                                    └─► (loop if issues, max 2) ──► END

Key ideas:
- City-block decomposition: the engineer produces one self-contained
  function/class per iteration with explicit contracts.
- ExecutableFeedback: generated code runs in a subprocess sandbox.
- Haiku Context Bombardment (the differentiator): feed Haiku all context,
  cut access, then fire 100 traceability/contract/invariant questions.
  If Haiku answers vaguely → real gaps exist.
- Opus reviewer is invoked ONLY when haiku_score < 70 OR critical gaps exist
  (cost-first: keep most runs at Tier B+, escalate to S only when needed).

Usage:
    from bin.core.code_quality import CodeQualityPipeline
    result = CodeQualityPipeline().run(
        spec="Implement parse_csv(path) that returns list[dict]...",
        context="Module: bin/core/utils.py. Stdlib only.",
        city_block_name="parse_csv",
    )
    print(result.code, result.haiku_score, result.gaps)
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from typing_extensions import TypedDict

from langgraph.graph import START, END, StateGraph
from langgraph.checkpoint.memory import InMemorySaver

from bin.core.dispatch import dispatch
from bin.core.logging_config import get_logger as _get_logger

log = _get_logger(__name__)

# Agents (defined in AGENT_ROUTING / openrouter_wrapper.py)
_OPT_AGENT = "opt-analyst"        # NIM Mistral 675B — optimization analysis
_ENGINEER_AGENT = "code-engineer"  # NIM DeepSeek V4 Flash — code generation
_PROBE_AGENT = "context-probe"     # Anthropic Haiku — bombardment
_REVIEWER_AGENT = "code-reviewer"  # Anthropic Opus — strict review

_MAX_ITERATIONS = 2
_HAIKU_SCORE_THRESHOLD = 70  # below this (or with critical gaps) → escalate to Opus
_OPUS_COST_PER_CALL = 0.20   # rough USD estimate per Opus review turn


# ── Sandbox ──────────────────────────────────────────────────────────────────


def _run_in_sandbox(code: str, timeout: int = 10) -> dict:
    """
    Execute generated code in an isolated subprocess.

    Returns {"stdout", "stderr", "returncode", "ok"}. Never raises; a syntax
    error, runtime error, or timeout is reported via the returned dict.
    """
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".py", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(code)
            tmp_path = fh.name

        # Minimal env — no inherited secrets; the sandbox just checks the code runs.
        safe_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": tempfile.gettempdir(),
            "PYTHONUNBUFFERED": "1",
        }
        proc = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=safe_env,
            cwd=tempfile.gettempdir(),
        )
        return {
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
            "returncode": proc.returncode,
            "ok": proc.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": f"timeout after {timeout}s", "returncode": -1, "ok": False}
    except Exception as _exc:
        return {"stdout": "", "stderr": f"sandbox error: {_exc}", "returncode": -1, "ok": False}
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _extract_code(raw: str) -> str:
    """Pull the first fenced code block from an LLM response; else return as-is."""
    if not raw:
        return ""
    m = re.search(r"```(?:python|py)?\s*\n(.*?)```", raw, re.DOTALL)
    if m:
        return m.group(1).strip()
    return raw.strip()


# ── Haiku Context Bombardment ────────────────────────────────────────────────

QUESTION_CATEGORIES = [
    "traceability",   # trace X from input to output
    "contracts",      # what does function Y guarantee
    "invariants",     # what can never be None/empty in Z
    "dependencies",   # which module depends on what, undeclared
    "misalignment",   # name vs behaviour coherence
    "edge_cases",     # empty / null / negative input on W
]

# How many questions per category (sums to 100).
_CATEGORY_QUOTA = {
    "traceability": 20,
    "contracts": 20,
    "invariants": 15,
    "dependencies": 15,
    "misalignment": 15,
    "edge_cases": 15,
}

_CATEGORY_TEMPLATES = {
    "traceability": "Trace how the value of `{sym}` flows from input to output. What transforms it?",
    "contracts": "What does `{sym}` guarantee about its return value and its arguments?",
    "invariants": "What must NEVER be None, empty, or out of range inside `{sym}`?",
    "dependencies": "What does `{sym}` depend on (imports, globals, other functions) that is not passed in explicitly?",
    "misalignment": "Does the name `{sym}` match what it actually does? Where could a reader be misled?",
    "edge_cases": "What happens in `{sym}` with empty, null, negative, or malformed input?",
}


def _extract_symbols(code: str) -> list[str]:
    """Extract def/class names from the code (fallback: the module itself)."""
    syms = re.findall(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)", code, re.MULTILINE)
    syms += re.findall(r"^\s*class\s+([A-Za-z_]\w*)", code, re.MULTILINE)
    # Keep order, dedupe
    seen, out = set(), []
    for s in syms:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out or ["the module"]


def _generate_100_questions(code: str, spec: str) -> list[str]:
    """
    Generate 100 adversarial questions about the generated code.

    Distribution: 20 traceability, 20 contracts, 15 invariants,
                  15 dependencies, 15 misalignment, 15 edge_cases.
    Questions are templated over the symbols (functions/classes) found in
    the code, cycling through them so every symbol gets probed.
    """
    symbols = _extract_symbols(code)
    questions: list[str] = []
    for category, quota in _CATEGORY_QUOTA.items():
        template = _CATEGORY_TEMPLATES[category]
        for i in range(quota):
            sym = symbols[i % len(symbols)]
            questions.append(f"[{category}] " + template.format(sym=sym))
    return questions[:100]


def _haiku_bombardment(code: str, context: str, questions: list[str], timeout: int = 300) -> dict:
    """
    Phase 1 (ingest): feed Haiku all code + context in ONE call.
    Phase 2 (bombard): ask all questions, no new context allowed.
    Phase 3 (score): parse answers, extract gaps.

    Returns {"gaps": [...], "score": 0-100, "critical_gaps": [...], "raw": str}.
    """
    full_context = f"CODE:\n{code}\n\nCONTEXT:\n{context}"
    numbered = "\n".join(f"Q{i + 1}: {q}" for i, q in enumerate(questions))
    questions_prompt = (
        f"You have been given the CODE and CONTEXT above. You have 30 seconds; "
        f"assume you cannot read any more files. Answer ALL {len(questions)} "
        f"questions below in 1-2 sentences each. If you cannot answer confidently "
        f"from the given material, respond with exactly 'UNCERTAIN'.\n"
        f"Format strictly as:\nQ1: <answer>\nQ2: <answer>\n...\n\n{numbered}"
    )

    res = dispatch(_PROBE_AGENT, questions_prompt, context=full_context, timeout=timeout)
    raw = res.get("response", "") or ""

    return _score_bombardment(raw, questions)


def _score_bombardment(raw: str, questions: list[str]) -> dict:
    """Parse Haiku's batched answers and turn weak answers into gaps."""
    total = len(questions)
    answers: dict[int, str] = {}
    for m in re.finditer(r"Q(\d+)\s*:\s*(.+?)(?=\nQ\d+\s*:|\Z)", raw, re.DOTALL):
        idx = int(m.group(1))
        answers[idx] = m.group(2).strip()

    weak_markers = ("uncertain", "unsure", "i don't know", "not sure", "unclear", "cannot determine", "n/a")
    gaps: list[str] = []
    critical_gaps: list[str] = []
    answered_ok = 0

    for i, q in enumerate(questions, start=1):
        ans = answers.get(i, "")
        low = ans.lower()
        is_weak = (not ans) or any(mk in low for mk in weak_markers) or len(ans) < 12
        if is_weak:
            gap = f"Gap #{i} [{_category_of(q)}]: {q}"
            gaps.append(gap)
            if q.startswith("[invariants]") or q.startswith("[contracts]") or q.startswith("[traceability]"):
                critical_gaps.append(gap)
        else:
            answered_ok += 1

    score = int(round(100 * answered_ok / total)) if total else 0
    return {"gaps": gaps, "score": score, "critical_gaps": critical_gaps, "raw": raw}


def _category_of(question: str) -> str:
    m = re.match(r"\[(\w+)\]", question)
    return m.group(1) if m else "general"


# ── StateGraph ───────────────────────────────────────────────────────────────


class CodeQualityState(TypedDict, total=False):
    spec: str
    context: str
    city_block_name: str
    optimization_notes: str
    generated_code: str
    execution_result: dict
    bombardment: dict
    review: dict
    iteration: int
    final_code: str
    issues_found: bool
    cost_estimate: float
    used_opus: bool


def _node_optimization_analysis(state: CodeQualityState) -> dict:
    """Cheap pre-review of the spec/pseudocode before any code is generated."""
    spec = state["spec"]
    ctx = state.get("context", "")
    prompt = (
        "You are an optimization analyst. BEFORE any code is written, review "
        "this specification for: algorithmic complexity risks, missing edge "
        "cases, unclear contracts, and hidden dependencies. Output a concise "
        "bullet list of concrete recommendations.\n\n"
        f"SPEC:\n{spec}\n\nCONTEXT:\n{ctx}"
    )
    res = dispatch(_OPT_AGENT, prompt, timeout=60)
    return {"optimization_notes": res.get("response", ""), "iteration": 0}


def _node_engineer_cityblock(state: CodeQualityState) -> dict:
    """Generate ONE self-contained city-block (function/class) with contracts."""
    spec = state["spec"]
    ctx = state.get("context", "")
    block = state.get("city_block_name", "")
    opt_notes = state.get("optimization_notes", "")
    review = state.get("review") or {}
    iteration = state.get("iteration", 0)

    feedback = ""
    if iteration > 0 and review:
        feedback = (
            "\n\nThis is a revision. Fix the issues raised by review:\n"
            f"{review.get('feedback', '')}\n"
            "And close these gaps from the context probe:\n"
            + "\n".join(state.get("bombardment", {}).get("critical_gaps", [])[:10])
        )

    block_line = f"Implement ONLY the self-contained block `{block}`.\n" if block else ""
    prompt = (
        "You are a senior engineer. Produce ONE self-contained, correct, "
        "runnable Python block (function or class) with an explicit docstring "
        "stating its contract (args, returns, invariants). Use only stdlib "
        "unless the context says otherwise. Output the code in a single "
        "```python``` fenced block.\n\n"
        f"{block_line}"
        f"SPEC:\n{spec}\n\nCONTEXT:\n{ctx}\n\n"
        f"OPTIMIZATION NOTES:\n{opt_notes}{feedback}"
    )
    res = dispatch(_ENGINEER_AGENT, prompt, timeout=180)
    code = _extract_code(res.get("response", ""))
    return {"generated_code": code}


def _node_attack_block(state: CodeQualityState) -> dict:
    """ExecutableFeedback — run the block in the sandbox to catch crashes."""
    code = state.get("generated_code", "")
    result = _run_in_sandbox(code)
    return {"execution_result": result}


def _node_haiku_bombardment(state: CodeQualityState) -> dict:
    """30s ingest + 100 adversarial questions → gap report."""
    code = state.get("generated_code", "")
    ctx = state.get("context", "")
    questions = _generate_100_questions(code, state.get("spec", ""))
    bombardment = _haiku_bombardment(code, ctx, questions)
    return {"bombardment": bombardment}


def _node_reviewer(state: CodeQualityState) -> dict:
    """Opus strict review — only reached when gaps exceed threshold."""
    code = state.get("generated_code", "")
    exec_result = state.get("execution_result", {})
    bombardment = state.get("bombardment", {})
    iteration = state.get("iteration", 0)

    prompt = (
        "You are a strict code reviewer (Opus). Attack this code: find bugs, "
        "contract violations, uncovered edge cases, and technical debt. "
        "End your response with a line 'VERDICT: APPROVED' if the code is "
        "production-ready, or 'VERDICT: ISSUES' otherwise.\n\n"
        f"CODE:\n{code}\n\n"
        f"SANDBOX RESULT:\n{exec_result}\n\n"
        f"CONTEXT-PROBE GAPS:\n" + "\n".join(bombardment.get("gaps", [])[:20])
    )
    res = dispatch(_REVIEWER_AGENT, prompt, timeout=180)
    raw = res.get("response", "") or ""
    issues = "VERDICT: APPROVED" not in raw.upper()

    cost = state.get("cost_estimate", 0.0) + _OPUS_COST_PER_CALL
    return {
        "review": {"raw": raw, "feedback": raw, "issues_found": issues},
        "issues_found": issues,
        "iteration": iteration + 1,
        "final_code": code,
        "cost_estimate": cost,
        "used_opus": True,
    }


def _route_after_bombardment(state: CodeQualityState) -> str:
    """Escalate to Opus only if score is low or critical gaps exist."""
    bombardment = state.get("bombardment", {})
    score = bombardment.get("score", 0)
    critical = bombardment.get("critical_gaps", [])
    if score < _HAIKU_SCORE_THRESHOLD or critical:
        return "reviewer"
    return "finalize"


def _route_after_review(state: CodeQualityState) -> str:
    """Loop back to the engineer if issues remain and budget allows."""
    if state.get("issues_found") and state.get("iteration", 0) < _MAX_ITERATIONS:
        return "engineer_cityblock"
    return "finalize"


def _node_finalize(state: CodeQualityState) -> dict:
    return {"final_code": state.get("generated_code", "")}


# ── Result + Pipeline ────────────────────────────────────────────────────────


@dataclass
class CodeQualityResult:
    spec: str
    code: str = ""
    review_summary: str = ""
    optimization_notes: str = ""
    execution_ok: bool = False
    haiku_score: int = 0
    gaps: list[str] = field(default_factory=list)
    critical_gaps: list[str] = field(default_factory=list)
    iterations: int = 0
    total_latency_ms: int = 0
    cost_tier: str = "B+"


class CodeQualityPipeline:
    """
    dqiii8 MetaGPT-pattern pipeline.

    Unique features:
    - City-block decomposition (one function/class per iteration)
    - Haiku Context Bombardment (30s ingest → 100 adversarial questions)
    - Opus review ONLY when haiku_score < 70 or critical gaps exist
    - Full StateGraph with InMemorySaver checkpointing
    """

    def __init__(self):
        self._graph = self._build()
        self._checkpointer = InMemorySaver()
        self._compiled = self._graph.compile(checkpointer=self._checkpointer)

    def _build(self) -> StateGraph:
        b = StateGraph(CodeQualityState)
        b.add_node("optimization_analysis", _node_optimization_analysis)
        b.add_node("engineer_cityblock", _node_engineer_cityblock)
        b.add_node("attack_block", _node_attack_block)
        b.add_node("haiku_bombardment", _node_haiku_bombardment)
        b.add_node("reviewer", _node_reviewer)
        b.add_node("finalize", _node_finalize)

        b.add_edge(START, "optimization_analysis")
        b.add_edge("optimization_analysis", "engineer_cityblock")
        b.add_edge("engineer_cityblock", "attack_block")
        b.add_edge("attack_block", "haiku_bombardment")
        b.add_conditional_edges(
            "haiku_bombardment",
            _route_after_bombardment,
            {"reviewer": "reviewer", "finalize": "finalize"},
        )
        b.add_conditional_edges(
            "reviewer",
            _route_after_review,
            {"engineer_cityblock": "engineer_cityblock", "finalize": "finalize"},
        )
        b.add_edge("finalize", END)
        return b

    def run(self, spec: str, context: str = "", city_block_name: str = "") -> CodeQualityResult:
        t0 = time.time()
        thread_id = f"cq-{int(t0)}"
        final = self._compiled.invoke(
            {
                "spec": spec,
                "context": context,
                "city_block_name": city_block_name,
                "iteration": 0,
                "issues_found": False,
                "cost_estimate": 0.0,
                "used_opus": False,
            },
            config={"configurable": {"thread_id": thread_id}, "recursion_limit": 50},
        )

        bombardment = final.get("bombardment", {})
        exec_result = final.get("execution_result", {})
        review = final.get("review", {})

        return CodeQualityResult(
            spec=spec,
            code=final.get("final_code") or final.get("generated_code", ""),
            review_summary=review.get("raw", ""),
            optimization_notes=final.get("optimization_notes", ""),
            execution_ok=bool(exec_result.get("ok", False)),
            haiku_score=bombardment.get("score", 0),
            gaps=bombardment.get("gaps", []),
            critical_gaps=bombardment.get("critical_gaps", []),
            iterations=max(final.get("iteration", 0), 1),
            total_latency_ms=int((time.time() - t0) * 1000),
            cost_tier="S" if final.get("used_opus") else "B+",
        )


if __name__ == "__main__":
    import json

    _spec = " ".join(sys.argv[1:]) or "Implement add(a, b) that returns a + b with type checks."
    _r = CodeQualityPipeline().run(spec=_spec, context="Stdlib only.")
    print(json.dumps(_r.__dict__, indent=2, ensure_ascii=False))
