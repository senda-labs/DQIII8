"""
tests/test_token_tracking.py — Token tracking system tests

Verifies:
1. token_usage table exists in dqiii8.db
2. token_usage_daily view exists
3. log_token_usage() inserts correctly
4. log_to_db() calls log_token_usage() (end-to-end insert)
"""

import sqlite3
import sys
import time
from pathlib import Path

import pytest

DQIII8_ROOT = Path(__file__).parent.parent
DB_PATH = DQIII8_ROOT / "database" / "dqiii8.db"

sys.path.insert(0, str(DQIII8_ROOT))


@pytest.mark.requires_db
def test_token_usage_table_exists():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='token_usage'"
    )
    assert cur.fetchone() is not None, "token_usage table not found"
    conn.close()


@pytest.mark.requires_db
def test_token_usage_daily_view_exists():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view' AND name='token_usage_daily'"
    )
    assert cur.fetchone() is not None, "token_usage_daily view not found"
    conn.close()


@pytest.mark.requires_db
def test_token_usage_schema():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.execute("PRAGMA table_info(token_usage)")
    columns = {row[1] for row in cur.fetchall()}
    conn.close()
    required = {
        "id",
        "session_id",
        "model",
        "tier",
        "operation",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "cost_estimate",
        "source",
        "timestamp",
    }
    missing = required - columns
    assert not missing, f"Missing columns in token_usage: {missing}"


@pytest.mark.requires_db
def test_log_token_usage_inserts():
    from bin.core.openrouter_wrapper import log_token_usage

    session_id = f"test_session_{int(time.time())}"
    log_token_usage(
        session_id=session_id,
        model="test/model-7b",
        tier="C",
        operation="test_op",
        tokens_in=100,
        tokens_out=50,
        cost_estimate=0.0,
        source="pytest",
    )

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.execute(
        "SELECT input_tokens, output_tokens, total_tokens, tier, source "
        "FROM token_usage WHERE session_id = ? ORDER BY id DESC LIMIT 1",
        (session_id,),
    )
    row = cur.fetchone()
    conn.close()

    assert row is not None, "No row inserted by log_token_usage()"
    inp, out, total, tier, source = row
    assert inp == 100
    assert out == 50
    assert total == 150
    assert tier == "C"
    assert source == "pytest"


@pytest.mark.requires_db
def test_log_token_usage_daily_view_aggregates():
    from bin.core.openrouter_wrapper import log_token_usage

    session_id = f"test_daily_{int(time.time())}"
    log_token_usage(
        session_id=session_id,
        model="groq/llama-3.3-70b",
        tier="B",
        operation="daily_test",
        tokens_in=200,
        tokens_out=100,
        cost_estimate=0.0001,
        source="pytest",
    )

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.execute(
        "SELECT calls, total_input, total_output FROM token_usage_daily "
        "WHERE model = 'groq/llama-3.3-70b' AND day = date('now') "
        "ORDER BY calls DESC LIMIT 1"
    )
    row = cur.fetchone()
    conn.close()

    assert row is not None, "token_usage_daily view returned no rows for test model"
    calls, inp, out = row
    assert calls >= 1
    assert inp >= 200
    assert out >= 100


@pytest.mark.requires_db
def test_log_to_db_triggers_token_usage(monkeypatch):
    """log_to_db() should insert a row into token_usage via log_token_usage()."""
    from bin.core import openrouter_wrapper

    recorded = []
    original = openrouter_wrapper.log_token_usage

    def capture(*args, **kwargs):
        recorded.append((args, kwargs))
        original(*args, **kwargs)

    monkeypatch.setattr(openrouter_wrapper, "log_token_usage", capture)

    openrouter_wrapper.log_to_db(
        agent="test_agent",
        model="test-model",
        provider="ollama",
        tokens_in=10,
        tokens_out=5,
        duration_ms=100,
        success=True,
        session_id=f"test_log_to_db_{int(time.time())}",
    )

    assert len(recorded) == 1, "log_token_usage was not called by log_to_db()"
    args, _ = recorded[0]
    # args: session_id, model, tier, operation, tokens_in, tokens_out, cost_usd
    assert args[4] == 10  # tokens_in
    assert args[5] == 5  # tokens_out
    assert args[2] == "C"  # tier for ollama
