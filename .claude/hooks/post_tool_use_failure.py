#!/usr/bin/env python3
"""
DQIII8 Hook — PostToolUseFailure
Dedicated error capture for tool-level failures.

Triggered by Claude Code's PostToolUseFailure event (tool crash, permission
denied, network error, parse error — NOT Bash exit code != 0, which is
handled by the success=0 path in post_tool_use.py).

Actions:
  1. Classify error type from error_message keywords
  2. Infer agent name (same chain as post_tool_use.py)
  3. INSERT into error_log
  4. UPDATE agent_actions (mark failure if recent open record exists)

Silent always — exit 0, no stdout output.
Timeout: 2s hard limit.
"""

import json
import os
import signal
import sqlite3
import sys
import time

DQIII8_ROOT = os.environ.get("DQIII8_ROOT", "/root/dqiii8")
DB = os.path.join(DQIII8_ROOT, "database", "dqiii8.db")

# ── Timeout guard ─────────────────────────────────────────────────────────────


def _timeout_handler(signum, frame):
    sys.exit(0)


signal.signal(signal.SIGALRM, _timeout_handler)
signal.alarm(2)


# ── Error classification ──────────────────────────────────────────────────────

_ERROR_MAP = [
    ("FileNotFoundError", "file-not-found"),
    ("FileNotFound", "file-not-found"),
    ("No such file", "file-not-found"),
    ("PermissionError", "permission-denied"),
    ("Permission denied", "permission-denied"),
    ("Permission", "permission-denied"),
    ("TimeoutError", "timeout"),
    ("Timeout", "timeout"),
    ("timed out", "timeout"),
    ("SyntaxError", "syntax-error"),
    ("JSONDecodeError", "json-parse"),
    ("json.decoder", "json-parse"),
    ("ConnectionError", "connection-error"),
    ("ConnectionRefused", "connection-error"),
    ("Connection refused", "connection-error"),
    ("URLError", "connection-error"),
    ("ModuleNotFoundError", "import-error"),
    ("ImportError", "import-error"),
    ("AttributeError", "attribute-error"),
    ("KeyError", "key-error"),
    ("IndexError", "index-error"),
    ("TypeError", "type-error"),
    ("ValueError", "value-error"),
    ("OSError", "os-error"),
]


def _classify_error(error_message: str, tool_name: str) -> tuple[str, list[str]]:
    """
    Returns (error_type, keywords_list).
    error_type: semantic slug from _ERROR_MAP or "tool-error"
    keywords: up to 3 tags including tool name
    """
    tags = []
    matched_type = "unknown-error"

    for pattern, slug in _ERROR_MAP:
        if pattern.lower() in error_message.lower():
            matched_type = slug
            tags.append(slug)
            if len(tags) >= 2:
                break

    # Always include tool name as keyword
    tool_tag = tool_name.lower().replace(" ", "-")
    if tool_tag not in tags:
        tags.insert(0, tool_tag)

    # Cap at 3
    tags = tags[:3]
    return matched_type, tags


# ── Agent name resolution (mirrors post_tool_use.py) ─────────────────────────


def _resolve_agent(data: dict) -> str:
    session = data.get("session_id", "unknown")
    tool = data.get("tool_name", "")
    inp = data.get("tool_input", {}) or {}

    agent = os.environ.get("CLAUDE_AGENT_NAME", "")
    if not agent:
        agent = data.get("agent_id", data.get("agent_name", ""))
    if not agent:
        try:
            with open(f"/tmp/dqiii8_agent_{session}.json", encoding="utf-8") as _f:
                agent = json.load(_f).get("agent_type", "")
        except Exception:
            pass
    if not agent:
        agent = "claude-sonnet-4-6"

    # UUID inference (17 hex chars starting with 'a')
    if len(agent) == 17 and agent[0] == "a" and all(c in "0123456789abcdef" for c in agent[1:]):
        _fp = inp.get("file_path", inp.get("command", ""))
        if tool in ("Edit", "Write", "MultiEdit") and _fp.endswith(".py"):
            agent = "python-specialist"
        elif tool == "Bash" and any(
            k in _fp for k in ("git commit", "git push", "git branch", "git tag")
        ):
            agent = "git-specialist"
        else:
            agent = "claude-sonnet-4-6"

    return agent


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    session = data.get("session_id", "unknown")
    tool = data.get("tool_name", "unknown")
    error_message = (data.get("error_message") or data.get("error") or "")[:500]

    if not error_message:
        # No message to record
        sys.exit(0)

    if not os.path.exists(DB):
        sys.exit(0)

    agent = _resolve_agent(data)
    error_type, keywords = _classify_error(error_message, tool)
    now_ms = int(time.time() * 1000)

    try:
        conn = sqlite3.connect(DB, timeout=2)

        # INSERT into error_log
        conn.execute(
            "INSERT INTO error_log "
            "(timestamp, session_id, agent_name, error_type, error_message, "
            "keywords, resolved, lesson_added) "
            "VALUES (datetime('now'), ?, ?, ?, ?, ?, 0, 0)",
            (
                session,
                agent,
                f"{tool}Error",
                error_message,
                json.dumps(keywords),
            ),
        )

        # UPDATE agent_actions: mark the most recent open record for this tool as failed
        # "recent" = started within the last 10 seconds (10000ms)
        conn.execute(
            """
            UPDATE agent_actions
            SET success=0, error_message=?, end_time_ms=?
            WHERE id=(
                SELECT id FROM agent_actions
                WHERE session_id=? AND tool_used=? AND end_time_ms IS NULL
                  AND start_time_ms >= ?
                ORDER BY id DESC LIMIT 1)
            """,
            (error_message[:500], now_ms, session, tool, now_ms - 10000),
        )

        conn.commit()
        conn.close()
    except Exception:
        pass  # never block on logging failure

    sys.exit(0)


if __name__ == "__main__":
    main()
