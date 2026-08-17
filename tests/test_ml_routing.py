"""
tests/test_ml_routing.py — ML routing classifier tests

Verifies:
1. classify_task_complexity() returns correct tier for each task type
2. classify_cc_tier() (original binary) still works correctly
3. token_usage table stores task_complexity
4. log_token_usage() accepts task_complexity param
"""

import sqlite3
import sys
import time
from pathlib import Path

import pytest

DQIII8_ROOT = Path(__file__).parent.parent
DB_PATH = DQIII8_ROOT / "database" / "dqiii8.db"
SCHEMA_V2_SQL = (DQIII8_ROOT / "database" / "schema_v2.sql").read_text(encoding="utf-8")
sys.path.insert(0, str(DQIII8_ROOT))

from bin.orchestrator import (
    classify_cc_tier,
    classify_task_complexity,
    detect_task_type,
    select_tier,
    should_fallback,
)


def _isolated_db(tmp_path):
    """Build a throwaway DB from the real schema_v2.sql SSOT.

    log_token_usage()/log_to_db() write to the append-only, DB-trigger-enforced
    agent_actions/token_usage audit tables — pointing them at the real production
    DB from a test run permanently polluted a log that can't be deleted back out.
    """
    db_path = tmp_path / "database" / "dqiii8.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_V2_SQL)
    conn.commit()
    conn.close()
    return db_path

# ── classify_task_complexity ──────────────────────────────────────────────────


class TestClassifyTaskComplexity:
    def test_read_only_grep(self):
        assert classify_task_complexity("grep TODO in all python files") == "READ_ONLY"

    def test_read_only_ls(self):
        assert classify_task_complexity("ls the tests directory") == "READ_ONLY"

    def test_read_only_git_log(self):
        assert classify_task_complexity("git log last 10 commits") == "READ_ONLY"

    def test_read_only_explain(self):
        assert (
            classify_task_complexity("explain how the classifier works") == "READ_ONLY"
        )

    def test_read_only_find(self):
        assert (
            classify_task_complexity("find all .py files with import sqlite3")
            == "READ_ONLY"
        )

    def test_simple_write_pytest(self):
        assert (
            classify_task_complexity("run pytest tests/test_smoke.py") == "SIMPLE_WRITE"
        )

    def test_simple_write_commit(self):
        assert (
            classify_task_complexity("git add and commit these changes")
            == "SIMPLE_WRITE"
        )

    def test_simple_write_push(self):
        assert classify_task_complexity("git push to origin main") == "SIMPLE_WRITE"

    def test_simple_write_test(self):
        assert (
            classify_task_complexity("test the token tracking module") == "SIMPLE_WRITE"
        )

    def test_code_gen_create(self):
        assert (
            classify_task_complexity("create a function to parse JSON config")
            == "CODE_GEN"
        )

    def test_code_gen_implement(self):
        assert (
            classify_task_complexity("implement a retry decorator for API calls")
            == "CODE_GEN"
        )

    def test_code_gen_refactor(self):
        assert classify_task_complexity("refactor the auth module") == "CODE_GEN"

    def test_code_gen_write(self):
        assert (
            classify_task_complexity("write a class that wraps sqlite3 connections")
            == "CODE_GEN"
        )

    def test_architecture_design(self):
        assert (
            classify_task_complexity(
                "design a caching system for the embeddings pipeline"
            )
            == "ARCHITECTURE"
        )

    def test_architecture_plan(self):
        assert (
            classify_task_complexity("plan the migration from SQLite to PostgreSQL")
            == "ARCHITECTURE"
        )

    def test_architecture_long_prompt(self):
        long = "x " * 260  # > 500 chars
        assert classify_task_complexity(long) == "ARCHITECTURE"

    def test_architecture_keyword(self):
        assert (
            classify_task_complexity("diseña el sistema de routing de modelos")
            == "ARCHITECTURE"
        )

    def test_critical_production(self):
        assert classify_task_complexity("deploy to production server") == "CRITICAL"

    def test_critical_security(self):
        assert (
            classify_task_complexity("security audit of the auth module") == "CRITICAL"
        )

    def test_critical_credentials(self):
        assert (
            classify_task_complexity("rotate the API credentials in .env") == "CRITICAL"
        )

    def test_critical_vulnerability(self):
        assert (
            classify_task_complexity("fix the CVE vulnerability in dependencies")
            == "CRITICAL"
        )

    def test_critical_takes_priority_over_read(self):
        # Even if it looks like a read, security keywords escalate
        assert (
            classify_task_complexity("grep for hardcoded credentials in production")
            == "CRITICAL"
        )


# ── classify_cc_tier (original binary classifier) ────────────────────────────


class TestClassifyCcTier:
    def test_planning_returns_a(self):
        assert classify_cc_tier("plan the new feature") == "A"

    def test_design_returns_a(self):
        assert classify_cc_tier("design the API structure") == "A"

    def test_exec_verb_returns_a(self):
        assert classify_cc_tier("implement the login function") == "A"

    def test_long_prompt_returns_a(self):
        assert classify_cc_tier("x " * 200) == "A"

    def test_simple_query_returns_c(self):
        assert classify_cc_tier("what is the bge-m3 model") == "C"

    def test_how_does_returns_c(self):
        assert classify_cc_tier("how does the domain classifier work") == "C"

    def test_git_exec_kw_returns_a(self):
        assert classify_cc_tier("run git status") == "A"


# ── detect_task_type ──────────────────────────────────────────────────────────


class TestDetectTaskType:
    def test_planning_keywords(self):
        assert detect_task_type("plan the migration") == "planning"
        assert detect_task_type("diseña la arquitectura") == "planning"
        assert detect_task_type("analyze the bottlenecks") == "planning"

    def test_execution_verbs(self):
        assert detect_task_type("create a function") == "execution"
        assert detect_task_type("fix the bug in auth") == "execution"
        assert detect_task_type("implement retry logic") == "execution"

    def test_execution_keywords(self):
        assert detect_task_type("there is a traceback in the logs") == "execution"
        assert detect_task_type("refactor this module") == "execution"

    def test_knowledge_queries(self):
        assert detect_task_type("what is bge-m3") == "knowledge"
        assert detect_task_type("how does the orchestrator work") == "knowledge"
        assert detect_task_type("hola") == "knowledge"

    def test_pure_function_no_side_effects(self):
        r1 = detect_task_type("plan it")
        r2 = detect_task_type("plan it")
        assert r1 == r2 == "planning"


# ── select_tier ───────────────────────────────────────────────────────────────


class TestSelectTier:
    def test_planning_maps_to_a(self):
        assert select_tier("planning") == "A"

    def test_execution_maps_to_a(self):
        assert select_tier("execution") == "A"

    def test_knowledge_short_maps_to_c(self):
        assert select_tier("knowledge", 0) == "C"
        assert select_tier("knowledge", 150) == "C"

    def test_knowledge_long_prompt_maps_to_a(self):
        assert select_tier("knowledge", 301) == "A"
        assert select_tier("knowledge", 1000) == "A"

    def test_boundary_300_chars(self):
        assert select_tier("knowledge", 300) == "C"
        assert select_tier("knowledge", 301) == "A"


# ── should_fallback ───────────────────────────────────────────────────────────


class TestShouldFallback:
    def test_failure_always_escalates(self):
        assert should_fallback("A", success=False) is True
        assert should_fallback("C", success=False) is True

    def test_success_c_tier_no_escalation(self):
        assert should_fallback("C", success=True, output="some output") is False

    def test_short_output_escalates(self):
        assert should_fallback("A", success=True, output="too short", prompt_len=150) is True

    def test_long_output_no_escalation(self):
        long_output = "This is a detailed valid response. " * 20
        assert should_fallback("A", success=True, output=long_output, prompt_len=50) is False

    def test_failure_signal_escalates(self):
        assert should_fallback("A", success=True, output="I cannot do this task", prompt_len=50) is True
        assert should_fallback("A", success=True, output="no puedo completar eso", prompt_len=50) is True

    def test_short_prompt_no_escalation_on_short_output(self):
        assert should_fallback("A", success=True, output="ok", prompt_len=50) is False


# ── token_usage task_complexity column ───────────────────────────────────────


@pytest.mark.requires_db
def test_token_usage_has_task_complexity_column():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.execute("PRAGMA table_info(token_usage)")
    columns = {row[1] for row in cur.fetchall()}
    conn.close()
    assert (
        "task_complexity" in columns
    ), "task_complexity column missing from token_usage"


@pytest.mark.requires_db
def test_log_token_usage_stores_task_complexity(tmp_path, monkeypatch):
    from bin.core import openrouter_wrapper

    db_path = _isolated_db(tmp_path)
    monkeypatch.setattr(openrouter_wrapper, "DB_PATH", db_path)

    session_id = f"test_complexity_{int(time.time())}"
    openrouter_wrapper.log_token_usage(
        session_id=session_id,
        model="ollama/qwen2.5-coder:7b",
        tier="C",
        operation="test_code_gen",
        tokens_in=50,
        tokens_out=120,
        cost_estimate=0.0,
        source="pytest",
        task_complexity="CODE_GEN",
    )

    conn = sqlite3.connect(str(db_path))
    cur = conn.execute(
        "SELECT task_complexity FROM token_usage WHERE session_id = ? "
        "ORDER BY id DESC LIMIT 1",
        (session_id,),
    )
    row = cur.fetchone()
    conn.close()

    assert row is not None
    assert row[0] == "CODE_GEN"


@pytest.mark.requires_db
def test_log_to_db_passes_task_complexity(tmp_path, monkeypatch):
    from bin.core import openrouter_wrapper

    monkeypatch.setattr(openrouter_wrapper, "DB_PATH", _isolated_db(tmp_path))

    recorded = []
    original = openrouter_wrapper.log_token_usage

    def capture(*args, **kwargs):
        recorded.append(kwargs.get("task_complexity"))
        original(*args, **kwargs)

    monkeypatch.setattr(openrouter_wrapper, "log_token_usage", capture)

    openrouter_wrapper.log_to_db(
        agent="test_agent",
        model="test-model",
        provider="ollama",
        tokens_in=10,
        tokens_out=5,
        duration_ms=50,
        success=True,
        session_id=f"test_passthrough_{int(time.time())}",
        task_complexity="ARCHITECTURE",
    )

    assert len(recorded) == 1
    assert recorded[0] == "ARCHITECTURE"
