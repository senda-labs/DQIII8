#!/usr/bin/env python3
"""hpt_poller — reconciliation + retry poller for human_pending_tasks.

Scope: the poller slice of jarvis-control3/architecture/07-durable-worker.md.
hpt_worker.py / hpt_expiry_cron.py / hpt_agent_dispatcher.py are OUT OF SCOPE.

For each row `status='pending' AND archived=0 AND is_test=0`:

  1. If a `notify_ok` event exists in the ledger -> Telegram was already delivered.
     Reconcile status pending->notified via a CAS UPDATE (status+version guard),
     WITHOUT resending. Idempotency comes from the ledger, NOT from
     `notified_at IS NULL` (which would resend a message that was already sent
     when only the status UPDATE had failed).

  2. If no `notify_ok` and notify_count >= _MAX_NOTIFY -> exhausted. The frozen
     state machine (09-state-machine-triggers.md) FORBIDS pending->failed
     (RAISE(ABORT)); the only legal terminal edge here is pending->cancelled.
     Transition to cancelled/resolution_outcome='discarded'/last_error=
     'notify_exhausted' via CAS and alert the operator (error channel, not hpt:).

  3. Otherwise claim-to-notify: a CAS UPDATE that bumps notify_count/next_retry_at/
     version but does NOT touch status (so it never hits the transition trigger),
     guarded by status='pending' AND version=:v AND next_retry_at due. If it wins
     the row (rowcount==1), send_telegram ONCE (it already retries 3x internally;
     no extra retry loop here), then either notify_ok + pending->notified on
     success, or leave last_error on failure and let the next tick retry.

The systemd timer is Type=oneshot with no overlap; the claim-to-notify CAS also
covers a manual `systemctl start` racing the timer, so no external lock is needed.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bin.core.db import get_db
from bin.core.human_pending import events
from bin.core.logging_config import get_logger
from bin.core.notify import notify, send_telegram

log = get_logger("hpt_poller")

_BUSY_TIMEOUT_MS = 5000
_MAX_NOTIFY = 5  # plan decision (Q1): threshold not fixed in 03-notification.md


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _next_retry_iso(notify_count: int) -> str:
    """Exponential-ish backoff, capped, layered on top of the 2-minute timer."""
    delay_min = min(2 ** notify_count, 30)
    return (datetime.now(timezone.utc) + timedelta(minutes=delay_min)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _notify_ok_event(conn, task_id: str):
    """Return the most recent notify_ok event row for task_id, or None."""
    return conn.execute(
        "SELECT ts, detail FROM human_pending_events "
        "WHERE task_id=:id AND event='notify_ok' ORDER BY id DESC LIMIT 1",
        {"id": task_id},
    ).fetchone()


def _message_id_from_detail(detail: str | None) -> str | None:
    if not detail:
        return None
    try:
        return json.loads(detail).get("message_id")
    except Exception:
        return None


def _reconcile(row) -> None:
    """Ledger has notify_ok: fix status pending->notified, no resend."""
    task_id = row["id"]
    with get_db(busy_timeout_ms=_BUSY_TIMEOUT_MS) as conn:
        ok_event = _notify_ok_event(conn, task_id)
        if ok_event is None:
            return  # raced away since the snapshot; skip
        notified_at = ok_event["ts"] or _now_iso()
        msg_id = _message_id_from_detail(ok_event["detail"])
        cur = conn.execute(
            "UPDATE human_pending_tasks SET status='notified', notified_at=:notified_at, "
            "notify_count=notify_count+1, notification_msg_id=COALESCE(:mid, notification_msg_id), "
            "updated_at=:now, version=version+1 "
            "WHERE id=:id AND status='pending' AND version=:v",
            {"notified_at": notified_at, "mid": msg_id, "now": _now_iso(),
             "id": task_id, "v": row["version"]},
        )
        if cur.rowcount == 1:
            events.insert_event(task_id, "reconciled",
                                {"notified_at": notified_at}, conn=conn)
            log.info("reconciled pending->notified (no resend): %s", task_id)


def _exhaust(row) -> None:
    """No notify_ok and notify_count >= _MAX_NOTIFY: legal terminal edge
    pending->cancelled (pending->failed is illegal / RAISE(ABORT))."""
    task_id = row["id"]
    with get_db(busy_timeout_ms=_BUSY_TIMEOUT_MS) as conn:
        cur = conn.execute(
            "UPDATE human_pending_tasks SET status='cancelled', "
            "resolution_outcome='discarded', last_error='notify_exhausted', "
            "resolved_at=:now, resolved_by='hpt_poller', updated_at=:now, version=version+1 "
            "WHERE id=:id AND status='pending' AND version=:v",
            {"now": _now_iso(), "id": task_id, "v": row["version"]},
        )
        if cur.rowcount == 1:
            events.insert_event(task_id, "poller_exhausted",
                                {"notify_count": row["notify_count"]}, conn=conn)
            log.warning("poller_exhausted -> cancelled/discarded: %s", task_id)
            _alerted = True
        else:
            _alerted = False
    if _alerted:
        notify(
            f"⚠️ hpt_poller: tarea {task_id} ({row['project']}/{row['blocking_type']}) "
            f"agotó {_MAX_NOTIFY} intentos de notificación → cancelled/discarded."
        )


def _claim_and_notify(row) -> None:
    """No notify_ok yet: atomically claim the row for a send attempt, then send once."""
    task_id = row["id"]
    now = _now_iso()
    with get_db(busy_timeout_ms=_BUSY_TIMEOUT_MS) as conn:
        cur = conn.execute(
            "UPDATE human_pending_tasks SET notify_count=notify_count+1, "
            "next_retry_at=:next, version=version+1, updated_at=:now "
            "WHERE id=:id AND status='pending' AND version=:v "
            "AND (next_retry_at IS NULL OR next_retry_at <= :now)",
            {"next": _next_retry_iso(row["notify_count"]), "now": now,
             "id": task_id, "v": row["version"]},
        )
        won = cur.rowcount == 1
    if not won:
        return  # not due yet, or lost the CAS to another instance

    claimed_version = row["version"] + 1

    text = f"⚠️ {row['project']} bloqueado ({row['blocking_type']})\n{(row['description'] or '')[:400]}"
    reply_markup = {"inline_keyboard": [[{"text": "Reanudar", "callback_data": f"hpt:{task_id}"}]]}
    events.insert_event(task_id, "notify_attempt", {"notify_count": row["notify_count"] + 1})
    result = send_telegram(text, parse_mode=None, reply_markup=reply_markup,
                           chat_id=row["allowed_chat_id"])

    if result.ok:
        # Ledger BEFORE the status UPDATE — same ordering invariant as
        # register_and_notify(): notify_ok is the reconciliation signal.
        events.insert_event(task_id, "notify_ok", {"message_id": result.message_id})
        try:
            with get_db(busy_timeout_ms=_BUSY_TIMEOUT_MS) as conn:
                cur = conn.execute(
                    "UPDATE human_pending_tasks SET status='notified', notified_at=:now, "
                    "notification_msg_id=:mid, updated_at=:now, version=version+1 "
                    "WHERE id=:id AND status='pending' AND version=:v",
                    {"now": _now_iso(), "mid": result.message_id,
                     "id": task_id, "v": claimed_version},
                )
            if cur.rowcount == 1:
                log.info("poller notified pending->notified: %s", task_id)
            else:
                events.insert_event(task_id, "status_update_failed",
                                    {"reason": "cas_miss_after_send"})
        except Exception as e:
            events.insert_event(task_id, "status_update_failed", {"error": str(e)})
    else:
        events.insert_event(task_id, "notify_failed", {"error": result.error})
        try:
            with get_db(busy_timeout_ms=_BUSY_TIMEOUT_MS) as conn:
                conn.execute(
                    "UPDATE human_pending_tasks SET last_error=:err, updated_at=:now "
                    "WHERE id=:id AND status='pending'",
                    {"err": f"notify_failed:{result.error}", "now": _now_iso(), "id": task_id},
                )
        except Exception:
            pass  # next_retry_at is already set; next tick retries
        log.warning("poller notify_failed for %s: %s", task_id, result.error)


def run_once() -> None:
    with get_db(busy_timeout_ms=_BUSY_TIMEOUT_MS) as conn:
        rows = conn.execute(
            "SELECT id, version, notify_count, project, blocking_type, description, "
            "allowed_chat_id, next_retry_at, "
            "EXISTS(SELECT 1 FROM human_pending_events e "
            "       WHERE e.task_id=human_pending_tasks.id AND e.event='notify_ok') AS has_ok "
            "FROM human_pending_tasks "
            "WHERE status='pending' AND archived=0 AND is_test=0"
        ).fetchall()

    log.info("hpt_poller tick: %d pending row(s)", len(rows))
    for row in rows:
        try:
            if row["has_ok"]:
                _reconcile(row)
            elif row["notify_count"] >= _MAX_NOTIFY:
                _exhaust(row)
            else:
                _claim_and_notify(row)
        except Exception:
            log.exception("hpt_poller: row %s failed", row["id"])


if __name__ == "__main__":
    run_once()
