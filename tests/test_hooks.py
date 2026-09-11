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

ROOT_DIR = Path(__file__).parent.parent  # Current worktree or repo root
HOOKS = ROOT_DIR / ".claude" / "hooks"
SCHEMA_V2_SQL = (ROOT_DIR / "database" / "schema_v2.sql").read_text(encoding="utf-8")


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
        env={**os.environ, "DQIII8_ROOT": str(ROOT_DIR), "CLAUDE_SESSION_ID": "test-precompact-01"},
    )
    assert result.returncode == 0, f"precompact.py must exit 0, got {result.returncode}"
    out = json.loads(result.stdout)
    assert out == {}, f"precompact.py must output {{}}, got: {out}"


def test_precompact_postcompact_resume_snippet_roundtrip():
    """Rango 9 fix (2026-08-19 red-team audit): precompact.py builds a
    resume_snippet from agent_actions, postcompact.py reinjects it as
    'Recent activity' — the non-MCP replacement for context-mode's retired
    continuity snapshot. Uses an isolated tmp DB (tempfile + DQIII8_ROOT
    override + real schema_v2.sql), not the live production DB.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        db_dir = tmp / "database"
        db_dir.mkdir()
        (tmp / "tasks").mkdir()
        db_path = db_dir / "dqiii8.db"
        session_id = "test-resume-snippet-01"

        conn = sqlite3.connect(str(db_path))
        conn.executescript(SCHEMA_V2_SQL)
        for tool_used, file_path in [
            ("Read", ".claude/hooks/postcompact.py"),
            ("Bash", "pytest -q tests/test_hooks.py"),
            ("Edit", ".claude/hooks/precompact.py"),
        ]:
            conn.execute(
                "INSERT INTO agent_actions (session_id, agent_name, tool_used, file_path) "
                "VALUES (?, 'test-agent', ?, ?)",
                (session_id, tool_used, file_path),
            )
        conn.commit()
        conn.close()

        env = {**os.environ, "DQIII8_ROOT": str(tmp)}

        pre_payload = json.dumps({"session_id": session_id})
        pre_result = subprocess.run(
            [sys.executable, str(HOOKS / "precompact.py")],
            input=pre_payload,
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
        assert pre_result.returncode == 0

        post_payload = json.dumps({"session_id": session_id})
        post_result = subprocess.run(
            [sys.executable, str(HOOKS / "postcompact.py")],
            input=post_payload,
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
        assert post_result.returncode == 0
        out = json.loads(post_result.stdout)
        ctx = out.get("additionalContext", "")
        assert "Recent activity:" in ctx
        assert "Edit: .claude/hooks/precompact.py" in ctx
        assert "Bash: pytest -q tests/test_hooks.py" in ctx
        assert "Read: .claude/hooks/postcompact.py" in ctx
        # Chronological order (oldest first, matching insertion order above).
        read_pos = ctx.index("Read: .claude/hooks/postcompact.py")
        bash_pos = ctx.index("Bash: pytest -q tests/test_hooks.py")
        edit_pos = ctx.index("Edit: .claude/hooks/precompact.py")
        assert read_pos < bash_pos < edit_pos

        state_file = tmp / "tasks" / f"precompact_state_{session_id}.json"
        assert not state_file.exists(), "postcompact.py must delete the state file after reading it"


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
    assert fn("claude-sonnet-5") == 3, "sonnet must be tier 3 (paid)"
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


def test_pre_tool_use_resolves_project_from_cwd(tmp_path):
    """When stdin cwd is under my-projects/<name>/, agent_actions.project is set.

    Builds the tmp DB from the real schema_v2.sql SSOT rather than a hand-listed
    column subset — a hand-listed subset previously drifted behind real schema
    additions (e.g. the `worktree` column pre_tool_use.py's INSERT already
    writes), so the fixture silently exercised a schema pre_tool_use.py never
    actually sees in production and the INSERT it performs there failed loudly.
    """
    db_path = tmp_path / "database" / "dqiii8.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_V2_SQL)
    conn.commit()
    conn.close()

    # known_projects() validates the resolved slug against DQIII8_ROOT/my-projects/
    # (real DQIII8_ROOT has this; the isolated tmp DQIII8_ROOT below needs its own
    # copy or "intl-reports" fails validation and silently falls back to CORE_PROJECT).
    (tmp_path / "my-projects" / "intl-reports").mkdir(parents=True)

    cwd = "/root/dqiii8/my-projects/intl-reports/scripts"
    payload = json.dumps(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "session_id": "test-cwd-01",
            "agent_id": "test-agent",
            "cwd": cwd,
        }
    )
    result = subprocess.run(
        [sys.executable, str(HOOKS / "pre_tool_use.py")],
        input=payload,
        capture_output=True,
        text=True,
        timeout=10,
        env={**os.environ, "DQIII8_ROOT": str(tmp_path)},
    )
    assert result.returncode == 0
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT project FROM agent_actions WHERE session_id = 'test-cwd-01'"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "intl-reports"
