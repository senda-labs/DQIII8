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
import logging
import os
import signal
import sqlite3
import sys
import time

log = logging.getLogger("dqiii8." + __name__)

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
        # Correction G: the lookup file is keyed by agent_id, not session_id —
        # resolve session_id -> agent_id via agent_registry first (mirrors the
        # same fix in post_tool_use.py).
        try:
            _root = os.environ.get("DQIII8_ROOT", "/root/dqiii8")
            _direct = os.path.join(_root, "tmp", f"dqiii8_agent_{session}.json")
            if os.path.exists(_direct):
                with open(_direct, encoding="utf-8") as _f:
                    agent = json.load(_f).get("agent_type", "")
            else:
                _rconn = sqlite3.connect(DB, timeout=2)
                _rrow = _rconn.execute(
                    "SELECT agent_id FROM agent_registry WHERE parent_session=? "
                    "ORDER BY start_time DESC LIMIT 1",
                    (session,),
                ).fetchone()
                _rconn.close()
                if _rrow:
                    _lookup = os.path.join(_root, "tmp", f"dqiii8_agent_{_rrow[0]}.json")
                    if os.path.exists(_lookup):
                        with open(_lookup, encoding="utf-8") as _f:
                            agent = json.load(_f).get("agent_type", "")
        except Exception as e:
            log.debug("post_tool_use_failure: agent lookup file read failed (best-effort): %s", e)
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

    # Stage 0 (panel pass 1 finding): the error_log INSERT and the agent_actions
    # UPDATE must NOT share a transaction. With Stage 0 reviving post_tool_use.py's
    # close-out, both this hook and post_tool_use.py can race to close the same
    # row; the second closer hits trg_agent_actions_close_once's RAISE(ABORT) and
    # sqlite3 raises IntegrityError. That was previously caught by a single
    # try/except wrapping both statements — but since RAISE(ABORT) aborts before
    # conn.commit() is reached, the already-executed error_log INSERT was silently
    # rolled back too (never committed), losing the very error record this hook
    # exists to capture. Each statement now gets its own connection/transaction.
    try:
        conn = sqlite3.connect(DB, timeout=10)
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
        conn.commit()
        conn.close()
    except Exception as e:
        log.warning("post_tool_use_failure: error_log INSERT failed: %s", e, exc_info=True)  # never block on logging failure

    try:
        conn2 = sqlite3.connect(DB, timeout=10)
        # UPDATE agent_actions: mark the most recent open record for this tool as failed
        # "recent" = started within the last 10 seconds (10000ms)
        conn2.execute(
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
        conn2.commit()
        conn2.close()
    except sqlite3.IntegrityError as e:
        # Expected, documented residual (Correction H): post_tool_use.py already
        # closed this row (double-close race under trg_agent_actions_close_once).
        # Not an error — the row is already closed with the right data — but
        # logged distinctly so the race's real frequency stays observable.
        log.info("post_tool_use_failure: agent_actions already closed (double-close race): %s", e)
    except Exception as e:
        log.warning("post_tool_use_failure: agent_actions UPDATE failed: %s", e, exc_info=True)  # never block on logging failure

    sys.exit(0)


if __name__ == "__main__":
    main()
