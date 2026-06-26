#!/usr/bin/env python3
"""
DQIII8 — Director StateGraph (LangGraph)

Reimplements the 3-stage intent pipeline from ``bin/director.py`` as a
LangGraph ``StateGraph``:

    START
      └─► instinct_search ──(match, conf>0.7)──► enrich ──► END
                 │
             (no match)
                 └──► llm_classify ──(llm OK)──► enrich ──► END
                            │
                        (llm fail)
                            └──► keyword_fallback ──► enrich ──► END

The graph is a *drop-in alternative* to ``director.analyze_intent()``:
``DirectorGraph.invoke()`` returns the SAME dict schema. The classifier
nodes reuse the existing helpers from ``bin.director`` (single source of
truth) so behaviour does not drift.

Checkpointing uses ``InMemorySaver`` (SqliteSaver is not in the base
install); each run is additionally persisted to the ``graph_states``
SQLite table for durability/observability.

Usage:
    from bin.core.graph import DirectorGraph
    plan = DirectorGraph().invoke("backtesting momentum BTC")
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Optional

from typing_extensions import TypedDict

from langgraph.graph import START, END, StateGraph
from langgraph.checkpoint.memory import InMemorySaver

# Reuse director helpers as the single source of truth for classification.
import bin.director as _director  # noqa: E402

from bin.core.logging_config import get_logger as _get_logger

log = _get_logger(__name__)

DQIII8_ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
_DEFAULT_DB = str(DQIII8_ROOT / "database" / "dqiii8.db")

# Mirror of the local map inside director.analyze_intent() — keeps the
# model_router lookup identical between the two implementations.
_AGENT_TASK_TYPE_MAP: dict[str, str] = {
    "quant-analyst": "trading",
    "data-analyst": "analysis",
    "creative-writer": "writing",
    "python-specialist": "code",
    "git-specialist": "code",
    "research-analyst": "research",
    "content-automator": "pipeline",
}


class DirectorState(TypedDict, total=False):
    user_request: str
    instinct_result: Optional[tuple]   # (task_type, confidence) or None
    llm_result: Optional[dict]
    keyword_result: Optional[dict]
    final_plan: dict
    source: str                        # "instinct:0.95" | "llm" | "keyword_fallback"
    thread_id: str


# ── Nodes ─────────────────────────────────────────────────────────────────────


def _node_instinct_search(state: DirectorState) -> dict:
    """Stage 1 — high-confidence instincts fast path (no LLM)."""
    req = state["user_request"]
    task_type, confidence = _director._query_instincts_fast_path(req)
    if task_type:
        log.info("graph: instinct match %s (conf=%.2f)", task_type, confidence)
        agent = _director.TASK_AGENT_MAP.get(task_type, "orchestrator")
        tier = _director.TASK_TIER_MAP.get(task_type, 3)
        plan = {
            "task_type": task_type,
            "subtasks": [
                {
                    "description": req,
                    "agent": agent,
                    "parallel": False,
                    "depends_on": [],
                }
            ],
            "output_format": "report",
            "complexity": "medium",
            "recommended_tier": tier,
        }
        return {
            "instinct_result": (task_type, confidence),
            "final_plan": plan,
            "source": f"instinct:{confidence:.2f}",
        }
    return {"instinct_result": None}


def _node_llm_classify(state: DirectorState) -> dict:
    """Stage 2 — LLM intent classification (with single retry)."""
    req = state["user_request"]
    log.info("graph: querying LLM for intent analysis")
    plan = _director._call_llm_for_intent(req)
    if plan is None:
        log.info("graph: retrying LLM after failure")
        time.sleep(2)
        plan = _director._call_llm_for_intent(req)

    if plan is not None:
        return {"llm_result": plan, "final_plan": plan, "source": "llm"}
    return {"llm_result": None}


def _node_keyword_fallback(state: DirectorState) -> dict:
    """Stage 3 — static keyword fallback (last resort, no LLM)."""
    log.info("graph: LLM unavailable — using keyword fallback")
    plan = _director._keyword_fallback(state["user_request"])
    return {
        "keyword_result": plan,
        "final_plan": plan,
        "source": "keyword_fallback",
    }


def _node_enrich(state: DirectorState) -> dict:
    """Validate plan fields and enrich subtasks via model_router."""
    req = state["user_request"]
    plan = dict(state.get("final_plan") or {})

    plan.setdefault("task_type", "mixed")
    plan.setdefault("subtasks", [])
    plan.setdefault("output_format", "markdown")
    plan.setdefault("complexity", "medium")
    plan.setdefault("recommended_tier", 3)

    if not plan["subtasks"]:
        agent = _director.TASK_AGENT_MAP.get(plan["task_type"], "orchestrator")
        plan["subtasks"] = [
            {
                "description": req,
                "agent": agent,
                "parallel": False,
                "depends_on": [],
            }
        ]

    task_type = plan["task_type"]
    for subtask in plan["subtasks"]:
        subtask.setdefault("parallel", False)
        subtask.setdefault("depends_on", [])
        agent = subtask.get("agent", "")
        st_type = _AGENT_TASK_TYPE_MAP.get(agent, task_type)
        model, score = _director._get_model_for_task(st_type)
        subtask["recommended_model"] = model
        subtask["model_score"] = score

    plan["_source"] = state.get("source", "llm")
    return {"final_plan": plan}


# ── Routing ───────────────────────────────────────────────────────────────────


def _route_after_instinct(state: DirectorState) -> str:
    return "enrich" if state.get("instinct_result") else "llm_classify"


def _route_after_llm(state: DirectorState) -> str:
    return "enrich" if state.get("llm_result") else "keyword_fallback"


# ── Graph wrapper ─────────────────────────────────────────────────────────────


class DirectorGraph:
    """LangGraph implementation of the director intent pipeline."""

    def __init__(self, db_path: str = _DEFAULT_DB):
        self._db_path = db_path
        self._graph = self._build()
        self._checkpointer = InMemorySaver()
        self._compiled = self._graph.compile(checkpointer=self._checkpointer)

    def _build(self) -> StateGraph:
        builder = StateGraph(DirectorState)
        builder.add_node("instinct_search", _node_instinct_search)
        builder.add_node("llm_classify", _node_llm_classify)
        builder.add_node("keyword_fallback", _node_keyword_fallback)
        builder.add_node("enrich", _node_enrich)

        builder.add_edge(START, "instinct_search")
        builder.add_conditional_edges(
            "instinct_search",
            _route_after_instinct,
            {"enrich": "enrich", "llm_classify": "llm_classify"},
        )
        builder.add_conditional_edges(
            "llm_classify",
            _route_after_llm,
            {"enrich": "enrich", "keyword_fallback": "keyword_fallback"},
        )
        builder.add_edge("keyword_fallback", "enrich")
        builder.add_edge("enrich", END)
        return builder

    def invoke(self, user_request: str, thread_id: str | None = None) -> dict:
        """Run the graph and return the same dict format as analyze_intent()."""
        thread_id = thread_id or f"director-{uuid.uuid4().hex[:8]}"
        t0 = time.time()
        final_state = self._compiled.invoke(
            {"user_request": user_request, "thread_id": thread_id},
            config={"configurable": {"thread_id": thread_id}},
        )
        duration_ms = int((time.time() - t0) * 1000)
        try:
            self._persist_state(final_state, duration_ms)
        except Exception as _exc:  # persistence must never break the pipeline
            log.warning("graph_states persist failed: %s", _exc)
        return final_state["final_plan"]

    def _persist_state(self, state: DirectorState, duration_ms: int) -> None:
        """Manually persist the terminal state to the graph_states table."""
        if not Path(self._db_path).exists():
            return
        conn = sqlite3.connect(self._db_path, timeout=5)
        try:
            conn.execute(
                "INSERT INTO graph_states "
                "(thread_id, stage, state_json, source, user_request, duration_ms) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    state.get("thread_id", ""),
                    "enrich",
                    json.dumps(state.get("final_plan", {}), ensure_ascii=False),
                    state.get("source", ""),
                    state.get("user_request", ""),
                    duration_ms,
                ),
            )
            conn.commit()
        finally:
            conn.close()


if __name__ == "__main__":
    import sys

    req = " ".join(sys.argv[1:]) or "backtesting momentum strategy BTC 3 years"
    print(json.dumps(DirectorGraph().invoke(req), ensure_ascii=False, indent=2))
