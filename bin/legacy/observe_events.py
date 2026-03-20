"""
observe_events.py — Sync context-mode SessionDB → agent_actions (DQIII8).

Reads session_events from the context-mode DB for a given project_dir,
transforms types to the agent_actions schema, and inserts into jarvis_metrics.db.
Maintains a sync cursor in the sync_state table.

Direct usage:
    python3 bin/observe_events.py [--project-dir /root/jarvis] [--dry-run]

Called from stop.py at the end of each session.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from hashlib import sha256
from pathlib import Path

JARVIS_DB = Path("/root/jarvis/database/jarvis_metrics.db")
CONTEXT_MODE_DIR = Path.home() / ".claude" / "context-mode" / "sessions"

# context-mode type → (action_type, tool_used, success_override)
# success_override: None=keep 1, False=force 0
_TYPE_MAP: dict[str, tuple[str, str, bool | None]] = {
    "file_read": ("read", "Read", None),
    "file_edit": ("edit", "Edit", None),
    "file_write": ("write", "Write", None),
    "file_glob": ("search", "Glob", None),
    "file_search": ("search", "Grep", None),
    "git": ("git", "Bash", None),
    "error_tool": ("bash", "Bash", False),
    "task": ("task", "TodoWrite", None),
    "task_create": ("task", "TaskCreate", None),
    "task_update": ("task", "TaskUpdate", None),
    "plan_enter": ("plan", "EnterPlanMode", None),
    "plan_exit": ("plan", "ExitPlanMode", None),
    "plan_approved": ("plan", "ExitPlanMode", None),
    "plan_rejected": ("plan", "ExitPlanMode", False),
    "env": ("env", "Bash", None),
    "skill": ("skill", "Skill", None),
    "subagent_launched": ("agent", "Agent", None),
    "subagent_completed": ("agent", "Agent", None),
    "mcp": ("mcp", "mcp", None),
    "decision_question": ("decision", "AskUserQuestion", None),
    "worktree": ("env", "EnterWorktree", None),
    "cwd": ("env", "Bash", None),
    "rule": ("read", "Read", None),
    "rule_content": ("read", "Read", None),
}

_CREATE_SYNC_STATE = """
CREATE TABLE IF NOT EXISTS sync_state (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL UNIQUE,
    last_sync   TEXT,
    last_id     INTEGER DEFAULT 0,
    synced_rows INTEGER DEFAULT 0
);
"""


def _session_db_path(project_dir: str) -> Path:
    h = sha256(project_dir.encode()).hexdigest()[:16]
    return CONTEXT_MODE_DIR / f"{h}.db"


def _ensure_sync_state(conn: sqlite3.Connection) -> None:
    conn.execute(_CREATE_SYNC_STATE)
    conn.commit()


def _get_last_id(conn: sqlite3.Connection, source: str) -> int:
    row = conn.execute("SELECT last_id FROM sync_state WHERE source = ?", (source,)).fetchone()
    return row[0] if row else 0


def _update_sync_state(
    conn: sqlite3.Connection, source: str, last_id: int, rows_inserted: int
) -> None:
    conn.execute(
        """
        INSERT INTO sync_state (source, last_sync, last_id, synced_rows)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(source) DO UPDATE SET
            last_sync   = excluded.last_sync,
            last_id     = excluded.last_id,
            synced_rows = synced_rows + excluded.synced_rows
        """,
        (source, datetime.utcnow().isoformat(), last_id, rows_inserted),
    )
    conn.commit()


def _transform_event(ev: sqlite3.Row, project: str) -> dict | None:
    """Map a session_events row to an agent_actions dict. Returns None to skip."""
    mapping = _TYPE_MAP.get(ev["type"])
    if mapping is None:
        return None

    action_type, tool_used, success_override = mapping
    success = 0 if success_override is False else 1

    file_path: str | None = None
    if action_type in ("read", "edit", "write", "search"):
        raw = ev["data"] or ""
        # grep data format: "pattern in /path"
        file_path = raw.split(" in ")[-1].strip() if " in " in raw else raw or None

    error_message: str | None = None
    if success == 0:
        error_message = (ev["data"] or "")[:500]

    return {
        "timestamp": ev["created_at"],
        "session_id": ev["session_id"],
        "agent_name": "context-mode",
        "project": project,
        "tool_used": tool_used,
        "file_path": file_path,
        "action_type": action_type,
        "success": success,
        "error_message": error_message,
        "model_used": None,
        "tokens_used": None,
        "bytes_written": 0,
        "files_modified": json.dumps([file_path]) if file_path else "[]",
        "worktree": None,
        "skills_active": "[]",
        "blocked_by_hook": 0,
    }


def _insert_actions(conn: sqlite3.Connection, rows: list[dict], dry_run: bool = False) -> int:
    inserted = 0
    for row in rows:
        if dry_run:
            print(
                f"  [DRY] {row['action_type']:10} | {row['tool_used']:20} | "
                f"success={row['success']} | "
                f"{(row['file_path'] or row['session_id'] or '')[:60]}"
            )
            inserted += 1
            continue
        try:
            conn.execute(
                """
                INSERT INTO agent_actions
                    (timestamp, session_id, agent_name, project, tool_used,
                     file_path, action_type, success, error_message, model_used,
                     tokens_used, bytes_written, files_modified, worktree,
                     skills_active, blocked_by_hook)
                VALUES
                    (:timestamp, :session_id, :agent_name, :project, :tool_used,
                     :file_path, :action_type, :success, :error_message, :model_used,
                     :tokens_used, :bytes_written, :files_modified, :worktree,
                     :skills_active, :blocked_by_hook)
                """,
                row,
            )
            inserted += 1
            if row["success"] == 0:
                _keywords = json.dumps(
                    [
                        row["agent_name"],
                        row["tool_used"],
                        (row["file_path"] or "")[:20],
                    ]
                )
                conn.execute(
                    """
                    INSERT INTO error_log
                        (session_id, agent_name, error_type, error_message,
                         keywords, resolved, lesson_added)
                    VALUES (?, ?, ?, ?, ?, 0, 0)
                    """,
                    (
                        row["session_id"],
                        row["agent_name"],
                        row["tool_used"],
                        row["error_message"] or "no output",
                        _keywords,
                    ),
                )
        except sqlite3.Error as e:
            print(f"  WARN insert failed: {e}")
    if not dry_run:
        conn.commit()
    return inserted


def sync_context_mode_events(
    project_dir: str = "/root/jarvis",
    dry_run: bool = False,
) -> int:
    """
    Sync new context-mode session_events into DQIII8 agent_actions.
    Called from stop.py at session end. Returns rows inserted.
    """
    session_db = _session_db_path(project_dir)
    if not session_db.exists():
        return 0

    source_key = f"context-mode:{project_dir}"
    project_name = Path(project_dir).name

    jarvis_conn = sqlite3.connect(str(JARVIS_DB), timeout=10)
    jarvis_conn.row_factory = sqlite3.Row
    _ensure_sync_state(jarvis_conn)
    last_id = _get_last_id(jarvis_conn, source_key)

    ctx_conn = sqlite3.connect(str(session_db), timeout=5)
    ctx_conn.row_factory = sqlite3.Row
    try:
        rows = ctx_conn.execute(
            "SELECT * FROM session_events WHERE id > ? ORDER BY id ASC",
            (last_id,),
        ).fetchall()
    finally:
        ctx_conn.close()

    if not rows:
        jarvis_conn.close()
        return 0

    transformed: list[dict] = []
    max_id = last_id
    for ev in rows:
        record = _transform_event(ev, project=project_name)
        if record is not None:
            transformed.append(record)
        if ev["id"] > max_id:
            max_id = ev["id"]

    inserted = _insert_actions(jarvis_conn, transformed, dry_run=dry_run)

    if not dry_run and max_id > last_id:
        _update_sync_state(jarvis_conn, source_key, max_id, inserted)

    jarvis_conn.close()

    if inserted:
        print(f"[observe_events] synced {inserted} events ({project_name})")

    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync context-mode events → agent_actions")
    parser.add_argument(
        "--project-dir",
        default="/root/jarvis",
        help="Project directory (used to locate context-mode DB)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print without inserting")
    args = parser.parse_args()

    total = sync_context_mode_events(project_dir=args.project_dir, dry_run=args.dry_run)
    print(f"Done. Inserted: {total}")


if __name__ == "__main__":
    main()
