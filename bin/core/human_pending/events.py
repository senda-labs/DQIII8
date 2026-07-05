#!/usr/bin/env python3
"""Append-only event ledger for human_pending_tasks (jarvis-control3 v2).

Rationale (07-durable-worker.md): send_telegram() is not idempotent, so a crash
between a successful send and the status UPDATE would leave a row `pending` with
a message already delivered. A `notify_ok` event written to this ledger BEFORE
that UPDATE lets a reconciliation poller distinguish "already delivered, just fix
status" from "never delivered, retry send" — without a duplicate Telegram send.

This table is append-only: rows are never updated or deleted. get_db() does NOT
enable PRAGMA foreign_keys, so the FK to human_pending_tasks(id) is not enforced
at runtime — callers must always insert the task row before any of its events
(already the case, since register_and_notify() commits the INSERT first).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from bin.core.db import get_db

_BUSY_TIMEOUT_MS = 5000


def insert_event(task_id: str, event: str, detail: dict | None = None, *, conn=None) -> None:
    """Append one event to human_pending_events.

    `detail` (dict|None) is JSON-serialized — keep it free of secrets and raw
    payloads. Pass `conn` to enlist in an existing transaction (commits with that
    connection); omit it to open a short-lived auto-committing connection.
    """
    detail_json = json.dumps(detail, separators=(",", ":")) if detail is not None else None
    sql = "INSERT INTO human_pending_events (task_id, event, detail) VALUES (?, ?, ?)"
    params = (task_id, event, detail_json)
    if conn is not None:
        conn.execute(sql, params)
        return
    with get_db(busy_timeout_ms=_BUSY_TIMEOUT_MS) as c:
        c.execute(sql, params)
