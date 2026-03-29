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
sys.path.insert(0, str(DQIII8_ROOT))

from bin.orchestrator import classify_cc_tier, classify_task_complexity

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
def test_log_token_usage_stores_task_complexity():
    from bin.core.openrouter_wrapper import log_token_usage

    session_id = f"test_complexity_{int(time.time())}"
    log_token_usage(
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

    conn = sqlite3.connect(str(DB_PATH))
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
def test_log_to_db_passes_task_complexity(monkeypatch):
    from bin.core import openrouter_wrapper

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
