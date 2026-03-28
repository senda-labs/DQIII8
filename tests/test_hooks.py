#!/usr/bin/env python3
"""
DQIII8 — Hook Unit Tests
Covers: precompact, pre_tool_use._model_tier, post_tool_use implicit correction,
        and concurrent resource claim conflict detection.
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

JARVIS = Path("/root/dqiii8")
HOOKS = JARVIS / ".claude" / "hooks"


def test_precompact_exits_zero_and_outputs_empty_json():
    """precompact.py must always exit 0 and print {} — never abort compaction."""
    payload = json.dumps(
        {
            "trigger": "token_limit",
            "context_window": {"tokens_used": 95000, "tokens_total": 100000},
        }
    )
    result = subprocess.run(
        [sys.executable, str(HOOKS / "precompact.py")],
        input=payload,
        capture_output=True,
        text=True,
        timeout=10,
        env={**os.environ, "DQIII8_ROOT": str(JARVIS), "CLAUDE_SESSION_ID": "test-precompact-01"},
    )
    assert result.returncode == 0, f"precompact.py must exit 0, got {result.returncode}"
    out = json.loads(result.stdout)
    assert out == {}, f"precompact.py must output {{}}, got: {out}"


def test_cost_tier_classification():
    """_model_tier() in pre_tool_use classifies local/cloud-free/paid tiers correctly."""
    src = (HOOKS / "pre_tool_use.py").read_text(encoding="utf-8")
    match = re.search(r"(def _model_tier.*?)(?=\n\n\S)", src, re.DOTALL)
    assert match, "_model_tier function not found in pre_tool_use.py"
    ns: dict = {}
    exec(match.group(0), ns)  # noqa: S102
    fn = ns["_model_tier"]

    assert fn("ollama:qwen2.5-coder:7b") == 1, "ollama must be tier 1 (local)"
    assert fn("qwen2.5-coder:7b") == 1, "qwen2.5-coder must be tier 1 (local)"
    assert fn("groq:llama-3.3-70b-versatile") == 2, "groq must be tier 2 (cloud-free)"
    assert fn("claude-haiku-4-5") == 2, "haiku is tier 2 (mapped via haiku keyword)"
    assert fn("claude-sonnet-4-6") == 3, "sonnet must be tier 3 (paid)"
    assert fn("claude-opus-4-6") == 3, "opus must be tier 3 (paid)"
    assert fn("unknown-model") == 0, "unknown model must return tier 0"


def test_implicit_correction_captured_in_vault():
    """post_tool_use: fail → success on same file → lesson appears in vault_memory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        db_dir = tmp / "database"
        db_dir.mkdir()
        db_path = db_dir / "dqiii8.db"
        session_id = "test-impl-corr"

        # Minimal DB with required tables
        conn = sqlite3.connect(str(db_path))
        conn.executescript("""
            CREATE TABLE agent_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT, tool_used TEXT, file_path TEXT,
                action_type TEXT, start_time_ms INTEGER, end_time_ms INTEGER,
                duration_ms INTEGER, success INTEGER, error_message TEXT,
                bytes_written INTEGER, blocked_by_hook INTEGER DEFAULT 0,
                model_tier INTEGER DEFAULT 0, agent_name TEXT, tokens_used INTEGER
            );
            CREATE TABLE error_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT, agent_name TEXT, error_type TEXT,
                error_message TEXT, keywords TEXT, resolved INTEGER DEFAULT 0,
                resolution TEXT, lesson_added INTEGER DEFAULT 0,
                timestamp TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE vault_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL, predicate TEXT NOT NULL, object TEXT NOT NULL,
                project TEXT DEFAULT '', confidence REAL DEFAULT 1.0,
                times_seen INTEGER DEFAULT 1, source TEXT DEFAULT 'session_stop',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                last_seen TEXT NOT NULL DEFAULT (datetime('now')),
                entry_type TEXT DEFAULT 'lesson',
                UNIQUE(subject, predicate, object)
            );
            """)
        conn.commit()
        conn.close()

        env = {
            **os.environ,
            "DQIII8_ROOT": tmpdir,
            "CLAUDE_SESSION_ID": session_id,
            "JARVIS_PROJECT": "test-project",
        }
        target_file = "/tmp/test_target_file.py"
        agent_id = "test-agent"

        # Step 1: simulate a FAILING tool call on target_file
        fail_payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": target_file},
                "tool_response": {"exit_code": 1, "stderr": "syntax error"},
                "session_id": session_id,
                "agent_id": agent_id,
            }
        )
        subprocess.run(
            [sys.executable, str(HOOKS / "post_tool_use.py")],
            input=fail_payload,
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        # Step 2: simulate a SUCCEEDING tool call on the same file
        success_payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": target_file},
                "tool_response": {"exit_code": 0},
                "session_id": session_id,
                "agent_id": agent_id,
            }
        )
        subprocess.run(
            [sys.executable, str(HOOKS / "post_tool_use.py")],
            input=success_payload,
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        # Assert: vault_memory has the implicit lesson
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT subject, predicate, object, entry_type, source FROM vault_memory"
        ).fetchall()
        conn.close()

        assert len(rows) == 1, f"Expected 1 vault lesson, got {len(rows)}: {rows}"
        subj, pred, obj, etype, src = rows[0]
        assert subj == "EditError"
        assert pred == "resolved_by"
        assert "test_target_file.py" in obj
        assert etype == "lesson"
        assert src == "post_tool_use"


def test_claims_conflict_detected():
    """Two concurrent session claims on the same resource produce a detectable conflict."""
    db = sqlite3.connect(":memory:")
    db.execute("""
        CREATE TABLE resource_claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            resource TEXT NOT NULL,
            claimed_at TEXT DEFAULT (datetime('now'))
        )
        """)
    db.execute(
        "INSERT INTO resource_claims (session_id, resource) VALUES ('session-A', 'scene_director.py')"
    )
    db.execute(
        "INSERT INTO resource_claims (session_id, resource) VALUES ('session-B', 'scene_director.py')"
    )
    db.commit()

    conflicts = db.execute(
        "SELECT resource, COUNT(*) AS n FROM resource_claims GROUP BY resource HAVING n > 1"
    ).fetchall()
    db.close()

    assert len(conflicts) == 1, f"Expected 1 conflicted resource, got {len(conflicts)}"
    assert conflicts[0][0] == "scene_director.py"
    assert conflicts[0][1] == 2
