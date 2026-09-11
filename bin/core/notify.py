#!/usr/bin/env python3
"""Notification utilities for DQIII8. Uses direct API calls to avoid bot daemon conflicts."""

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests
from dotenv import load_dotenv

# Panel-review fix (round 22, Security P1 — causa raíz): esta línea solía insertar
# os.environ.get("DQIII8_ROOT", ...) — un valor controlado por env var — como sys.path[0]
# para TODO caller de notify.py, no solo para la unidad staged que la necesitaba. Cualquier
# proceso con DQIII8_ROOT apuntando a un árbol agent-writable (un drop-in de systemd, un env
# heredado, el propio calibracion-clock.service) cargaba bin/core/logging_config.py desde ese
# árbol — y notify.py lo importan stop.py y los hooks, que corren como root, así que era
# ejecución de código arbitraria como root. El propio fix de round 16 ya había establecido que
# `parents[2]` resuelve correctamente incluso en la copia staged bajo /opt/lier-calibracion
# (coincide con la raíz de esa copia) — DQIII8_ROOT nunca fue necesario para ESTA línea, solo
# para el breadcrumb path de abajo. sys.path[0] vuelve a ser puramente determinista, derivado de
# __file__, sin ninguna influencia de env var.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bin.core.logging_config import get_logger as _get_logger

log = _get_logger(__name__)

try:
    load_dotenv(Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8")) / ".env")
except OSError:
    # A caller running as a restricted user (e.g. a staged systemd unit with
    # EnvironmentFile= supplying its own token) may not have read access to
    # the root-owned .env — fall back to whatever is already in os.environ
    # instead of crashing on import.
    pass


@dataclass
class SendResult:
    ok: bool
    message_id: str | None = None
    error: str | None = None

    def __bool__(self) -> bool:
        return self.ok


def send_document(file_path: str | Path, caption: str = "") -> bool:
    """Send a file as a Telegram document."""
    token = (
        os.environ.get("DQIII8_BOT_TOKEN", "")
        or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        or os.environ.get("JARVIS_BOT_TOKEN", "")
    )
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        return False

    try:
        with open(file_path, "rb") as f:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendDocument",
                data={"chat_id": chat_id, "caption": caption[:1024]},
                files={"document": f},
                timeout=30,
            )
        return resp.status_code == 200
    except Exception:
        return False


def send_photo(file_path: str | Path, caption: str = "") -> bool:
    """Send a file as a Telegram photo (inline preview, not a document attachment)."""
    token = (
        os.environ.get("DQIII8_BOT_TOKEN", "")
        or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        or os.environ.get("JARVIS_BOT_TOKEN", "")
    )
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        return False

    try:
        with open(file_path, "rb") as f:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                data={"chat_id": chat_id, "caption": caption[:1024]},
                files={"photo": f},
                timeout=30,
            )
        return resp.status_code == 200
    except Exception:
        return False


# Alias for backwards compatibility
send_telegram_document = send_document


def send_telegram(
    message: str,
    *,
    parse_mode: str = None,
    reply_markup: dict = None,
    chat_id: str = None,
    retries: int = 3,
    max_backoff: float | None = None,
) -> SendResult:
    """Send a message via Telegram API directly (no bot daemon needed).

    `chat_id` overrides the global TELEGRAM_CHAT_ID (needed for human_pending_tasks
    rows, which target each row's own allowed_chat_id, not the global default).

    `max_backoff` caps the 429 retry_after sleep (audit 2026-09-09, panel-review
    round 22 Resilience P1): left `None` by default so every existing caller keeps
    its prior unbounded-flood-wait behavior — capping it repo-wide silently turned
    a Telegram delivery *delay* into a delivery *failure* for callers (e.g. the
    autonomous-mode permission escalation) whose correctness doesn't depend on any
    bounded-backoff assumption. Callers with a real join-timeout constraint (the
    calibración clock) opt in explicitly with their own ceiling.
    """
    token = (
        os.environ.get("DQIII8_BOT_TOKEN", "")
        or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        or os.environ.get("JARVIS_BOT_TOKEN", "")
    )
    resolved_chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token or not resolved_chat_id:
        return SendResult(ok=False, error="missing_token_or_chat_id")

    payload = {"chat_id": resolved_chat_id, "text": message[:4096]}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup

    last_error = None
    for attempt in range(max(1, retries)):
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json=payload,
                timeout=10,
            )
            if resp.status_code == 200:
                message_id = None
                try:
                    message_id = str(resp.json().get("result", {}).get("message_id"))
                except Exception:
                    pass
                return SendResult(ok=True, message_id=message_id)
            if resp.status_code == 429:
                retry_after = 1.0
                try:
                    retry_after = float(resp.json().get("parameters", {}).get("retry_after", 1.0))
                except Exception:
                    pass
                # Telegram flood-wait can return retry_after in the tens of seconds. Only
                # cap it when the caller opted in via max_backoff (its own join-timeout
                # constraint) — leave it unbounded otherwise so a slow-but-recoverable
                # flood-wait still delivers instead of silently failing (round 22 fix).
                if max_backoff is not None:
                    retry_after = min(retry_after, max_backoff)
                last_error = f"rate_limited_{resp.status_code}"
                if attempt < retries - 1:
                    time.sleep(retry_after)
                continue
            last_error = f"http_{resp.status_code}"
        except Exception as e:
            last_error = str(e)
        if attempt < retries - 1:
            time.sleep(2**attempt)

    return SendResult(ok=False, error=last_error)


def notify(message: str, parse_mode: str = None, max_backoff: float | None = None) -> SendResult:
    """Best-effort notification. Tries Telegram, falls back to print.

    Returns the SendResult so callers on rails that must not fail silently
    (health_check.py's alert/heartbeat paths) can detect and record delivery
    failure instead of only a log line nothing reads in production.

    `max_backoff` forwards to `send_telegram` (see its docstring, round 22 fix) —
    a caller with a real join-timeout budget (e.g. the calibración clock) must
    pass it explicitly here too, since `notify()` is the only entry point that
    plan's code actually calls.
    """
    result = send_telegram(message, parse_mode=parse_mode, max_backoff=max_backoff)
    # DQIII8_NOTIFY_DIR lets a caller isolate the breadcrumb into its own directory (e.g. a
    # sandboxed account that must not get a directory-level write grant on the shared DQIII8_ROOT
    # var/ tree, since deleting a directory entry needs write on the *parent* directory, not the
    # file) without repointing DQIII8_ROOT itself, which also drives the import path and .env
    # lookup above. Falls back to the pre-existing DQIII8_ROOT/var location when unset.
    notify_dir = os.environ.get(
        "DQIII8_NOTIFY_DIR", str(Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8")) / "var")
    )
    breadcrumb = Path(notify_dir) / "last_notify_failure"
    if not result:
        log.warning("notify fallback (Telegram unavailable): %s", message)
        try:
            breadcrumb.parent.mkdir(parents=True, exist_ok=True)
            breadcrumb.write_text(
                f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {result.error}\n"
            )
        except OSError:
            pass
    else:
        try:
            breadcrumb.unlink(missing_ok=True)
        except OSError:
            pass
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 notify.py <message>", file=sys.stderr)
        sys.exit(1)
    notify(sys.argv[1])
