#!/usr/bin/env python3
"""Single shared writer for human_pending_tasks (jarvis-control3 v2).

register_and_notify() is the ONLY sanctioned way to insert a blocking row —
resolver.py, cobrowsing_batch.py and any future MCP tool must call this
instead of reimplementing the INSERT, per
jarvis-control3/architecture/03-notification.md §7 (anti-divergence).

claim() is the only sanctioned way to move unblocked -> claimed (exec-once,
anti double-resume, per architecture/02-data-model.md §4).
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets as _pysecrets
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from bin.core.db import get_db
from bin.core.human_pending import events
from bin.core.notify import send_telegram

_BUSY_TIMEOUT_MS = 5000


def _emit(task_id: str, event: str, detail: dict | None = None) -> None:
    """Best-effort ledger write. Instrumentation must never change the caller's
    RegisterOutcome, so a ledger failure is swallowed (same policy as the
    best-effort notify UPDATE below)."""
    try:
        events.insert_event(task_id, event, detail)
    except Exception:
        pass
_BASE62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_DEFAULT_TTL = timedelta(hours=24)

RegisterOutcome = Literal["created", "deduped", "insert_failed", "notify_deferred"]


def default_origin_host() -> str:
    """origin_host CHECK constraint only allows 'netcup'|'hostinger'|'windows'.
    DQIII8_ORIGIN_HOST lets deploy pin this explicitly per-VPS; defaults to
    'netcup' (current VPS, see project_vps_migration memory)."""
    return os.environ.get("DQIII8_ORIGIN_HOST", "netcup")


@dataclass
class RegisterResult:
    outcome: RegisterOutcome
    id: str | None = None
    error: str | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _gen_id() -> str:
    """Opaque base62 id, server-generated, short enough for Telegram
    callback_data ('hpt:' + id must stay under the 64-byte limit)."""
    n = int.from_bytes(_pysecrets.token_bytes(16), "big")
    out = []
    while n:
        n, rem = divmod(n, 62)
        out.append(_BASE62[rem])
    return "".join(reversed(out)) or "0"


def _dedup_key(project: str, action_id: str, blocking_type: str, target_url: str | None) -> str:
    raw = f"{project}|{action_id}|{blocking_type}|{target_url or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _payload_hash(action_id: str, resume_args_json: str, checkpoint_ref: str | None) -> str:
    raw = f"{action_id}|{resume_args_json}|{checkpoint_ref or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()


def register_and_notify(
    *,
    project: str,
    action_id: str,
    blocking_type: str,
    description: str,
    target_url: str | None = None,
    screenshot_ref: str | None = None,
    priority: int = 3,
    resume_args: dict | None = None,
    checkpoint_ref: str | None = None,
    secret_ref: str | None = None,
    origin_host: str,
    created_by: str,
    origin_run_id: str | None,
    allowed_chat_id: str,
    is_test: bool = False,
) -> RegisterResult:
    """Insert a human_pending_tasks row and best-effort notify Telegram.

    Dedup on ux_pending_dedup (one live row per blocking signature) via
    INSERT ... ON CONFLICT DO NOTHING — a duplicate is a normal outcome
    ("deduped"), never an exception surfaced to the caller/scraper.
    """
    row_id = _gen_id()
    dedup_key = _dedup_key(project, action_id, blocking_type, target_url)
    resume_args_json = json.dumps(resume_args or {}, separators=(",", ":"))
    payload_hash = _payload_hash(action_id, resume_args_json, checkpoint_ref)
    now = _now_iso()
    expires_at = (datetime.now(timezone.utc) + _DEFAULT_TTL).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        with get_db(busy_timeout_ms=_BUSY_TIMEOUT_MS) as conn:
            cur = conn.execute(
                """
                INSERT INTO human_pending_tasks (
                    id, dedup_key, project, action_id, blocking_type, description,
                    target_url, screenshot_ref, priority, resume_args, checkpoint_ref,
                    secret_ref, payload_hash, created_by, origin_host, origin_run_id,
                    allowed_chat_id, status, created_at, updated_at, expires_at, is_test
                ) VALUES (
                    :id, :dedup_key, :project, :action_id, :blocking_type, :description,
                    :target_url, :screenshot_ref, :priority, :resume_args, :checkpoint_ref,
                    :secret_ref, :payload_hash, :created_by, :origin_host, :origin_run_id,
                    :allowed_chat_id, 'pending', :now, :now, :expires_at, :is_test
                )
                ON CONFLICT(dedup_key) WHERE status IN ('pending','notified','unblocked','claimed','resuming')
                DO NOTHING
                """,
                {
                    "id": row_id, "dedup_key": dedup_key, "project": project,
                    "action_id": action_id, "blocking_type": blocking_type,
                    "description": description[:500], "target_url": target_url,
                    "screenshot_ref": screenshot_ref, "priority": priority,
                    "resume_args": resume_args_json, "checkpoint_ref": checkpoint_ref,
                    "secret_ref": secret_ref, "payload_hash": payload_hash,
                    "created_by": created_by, "origin_host": origin_host,
                    "origin_run_id": origin_run_id, "allowed_chat_id": allowed_chat_id,
                    "now": now, "expires_at": expires_at, "is_test": int(is_test),
                },
            )
            if cur.rowcount == 0:
                return RegisterResult(outcome="deduped")
    except Exception as e:
        return RegisterResult(outcome="insert_failed", error=str(e))

    _emit(row_id, "inserted")

    if is_test:
        return RegisterResult(outcome="created", id=row_id)

    text = f"⚠️ {project} bloqueado ({blocking_type})\n{description[:400]}"
    reply_markup = {"inline_keyboard": [[{"text": "Reanudar", "callback_data": f"hpt:{row_id}"}]]}
    _emit(row_id, "notify_attempt")
    result = send_telegram(text, parse_mode=None, reply_markup=reply_markup, chat_id=allowed_chat_id)

    if result.ok:
        # Ledger BEFORE the status UPDATE (the whole point): a `notify_ok` event
        # proves delivery, so if the UPDATE below fails the row stays `pending`
        # but the poller reconciles it to `notified` WITHOUT a duplicate send.
        # sendMessage is not idempotent — do not reorder these two writes.
        _emit(row_id, "notify_ok", {"message_id": result.message_id})
        try:
            with get_db(busy_timeout_ms=_BUSY_TIMEOUT_MS) as conn:
                conn.execute(
                    "UPDATE human_pending_tasks SET status='notified', notified_at=:now, "
                    "notify_count=notify_count+1, notification_msg_id=:mid, updated_at=:now, "
                    "version=version+1 WHERE id=:id AND status='pending'",
                    {"now": _now_iso(), "mid": result.message_id, "id": row_id},
                )
        except Exception as e:
            # Delivered but status stuck at `pending`: leave the notify_ok ledger
            # entry as the reconciliation signal for hpt_poller.
            _emit(row_id, "status_update_failed", {"error": str(e)})
    else:
        _emit(row_id, "notify_failed", {"error": result.error})
        try:
            with get_db(busy_timeout_ms=_BUSY_TIMEOUT_MS) as conn:
                conn.execute(
                    "UPDATE human_pending_tasks SET last_error=:err, updated_at=:now "
                    "WHERE id=:id AND status='pending'",
                    {"err": f"notify_failed:{result.error}", "now": _now_iso(), "id": row_id},
                )
        except Exception:
            pass  # the row exists either way; the poller retries the send

    if not result.ok:
        return RegisterResult(outcome="notify_deferred", id=row_id, error=result.error)
    return RegisterResult(outcome="created", id=row_id)


def claim(task_id: str, claimed_by: str, version: int, lease_seconds: int = 300) -> bool:
    """Atomic exec-once claim: unblocked -> claimed, CAS on `version`.
    True iff this caller won it (rowcount==1); False means someone else
    already has it or the row moved on — caller must NOT execute."""
    now = datetime.now(timezone.utc)
    lease_until = (now + timedelta(seconds=lease_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_db(busy_timeout_ms=_BUSY_TIMEOUT_MS) as conn:
        cur = conn.execute(
            """
            UPDATE human_pending_tasks
               SET status='claimed', claimed_by=:claimed_by, lease_until=:lease_until,
                   version=version+1, updated_at=:now
             WHERE id=:id AND status='unblocked' AND version=:version
            """,
            {"claimed_by": claimed_by, "lease_until": lease_until, "now": now_iso,
             "id": task_id, "version": version},
        )
        return cur.rowcount == 1


def unblock(task_id: str) -> bool:
    """notified -> unblocked, idempotent (double-tap on the Telegram button
    is a no-op the second time: rowcount 0, not an error)."""
    with get_db(busy_timeout_ms=_BUSY_TIMEOUT_MS) as conn:
        cur = conn.execute(
            "UPDATE human_pending_tasks SET status='unblocked', version=version+1, "
            "updated_at=:now WHERE id=:id AND status='notified'",
            {"now": _now_iso(), "id": task_id},
        )
        return cur.rowcount == 1


def cancel(task_id: str, resolved_by: str) -> bool:
    """pending/notified/unblocked -> cancelled (manual discard). Terminal state,
    so resolved_at is set to satisfy the table's CHECK constraint."""
    with get_db(busy_timeout_ms=_BUSY_TIMEOUT_MS) as conn:
        cur = conn.execute(
            "UPDATE human_pending_tasks SET status='cancelled', resolved_by=:by, "
            "resolution_outcome='discarded', resolved_at=:now, updated_at=:now, "
            "version=version+1 WHERE id=:id AND status IN ('pending','notified','unblocked')",
            {"by": resolved_by, "now": _now_iso(), "id": task_id},
        )
        return cur.rowcount == 1


def get_task(task_id: str) -> dict | None:
    with get_db(busy_timeout_ms=_BUSY_TIMEOUT_MS) as conn:
        row = conn.execute("SELECT * FROM human_pending_tasks WHERE id=?", (task_id,)).fetchone()
        return dict(row) if row else None
