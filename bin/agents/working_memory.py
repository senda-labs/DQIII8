#!/usr/bin/env python3
"""Working memory — session-level context persistence via SQLite.

Session IDs by entry point:
- Telegram: "tg_{chat_id}"
- autonomous_loop: "auto_{YYYY-MM-DD}"
- Claude Code: "cc_{pid}"
- Default: "cc_{pid}" (falls back to DQIII8_SESSION_ID env var if set)
"""

import os
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = (
    Path(__file__).resolve().parent.parent.parent / "database" / "jarvis_metrics.db"
)


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def save_exchange(
    session_id: str,
    prompt: str,
    response: str,
    domain: str = None,
) -> None:
    """Save a prompt-response pair to working memory.

    Truncates both to 300 chars to keep the table lean.
    Fail-open: never raises — callers must not crash on memory failure.
    """
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO session_memory (session_id, role, content, domain) "
            "VALUES (?, ?, ?, ?)",
            (session_id, "user", prompt[:300], domain),
        )
        conn.execute(
            "INSERT INTO session_memory (session_id, role, content, domain) "
            "VALUES (?, ?, ?, ?)",
            (session_id, "assistant", response[:300], domain),
        )
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def get_session_context(session_id: str, max_exchanges: int = 3) -> str:
    """Return recent exchanges as a context string.

    Returns an empty string if no history exists for the session.
    Rows are returned newest-first, then reversed so the context reads
    chronologically.
    """
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT role, content FROM session_memory "
            "WHERE session_id = ? "
            "ORDER BY timestamp DESC LIMIT ?",
            (session_id, max_exchanges * 2),
        ).fetchall()
    except Exception:
        return ""
    finally:
        conn.close()

    if not rows:
        return ""

    rows = list(reversed(rows))
    lines = ["[Previous context from this session:]"]
    for row in rows:
        prefix = "User" if row["role"] == "user" else "Assistant"
        lines.append(f"{prefix}: {row['content']}")
    return "\n".join(lines)


def get_session_id(source: str = None, chat_id: int = None) -> str:
    """Generate a stable session ID based on entry-point source."""
    if source == "telegram" and chat_id:
        return f"tg_{chat_id}"
    if source == "autonomous":
        return f"auto_{datetime.now().strftime('%Y-%m-%d')}"
    return os.environ.get("DQIII8_SESSION_ID", f"cc_{os.getpid()}")


def cleanup_old_sessions(hours: int = 24) -> int:
    """Delete session_memory rows older than N hours.

    Returns the number of rows deleted.
    """
    conn = _get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM session_memory WHERE timestamp < datetime('now', ?)",
            (f"-{hours} hours",),
        )
        conn.commit()
        return cur.rowcount
    except Exception:
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    import sys

    if "--cleanup" in sys.argv:
        n = cleanup_old_sessions(24)
        print(f"Cleaned {n} old session memory entries")
