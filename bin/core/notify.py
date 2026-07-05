#!/usr/bin/env python3
"""Notification utilities for DQIII8. Uses direct API calls to avoid bot daemon conflicts."""

import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bin.core.logging_config import get_logger as _get_logger
log = _get_logger(__name__)


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


# Alias for backwards compatibility
send_telegram_document = send_document

def send_telegram(message: str, *, parse_mode: str = None, reply_markup: dict = None,
                   chat_id: str = None, retries: int = 3) -> SendResult:
    """Send a message via Telegram API directly (no bot daemon needed).

    `chat_id` overrides the global TELEGRAM_CHAT_ID (needed for human_pending_tasks
    rows, which target each row's own allowed_chat_id, not the global default).
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
                last_error = f"rate_limited_{resp.status_code}"
                if attempt < retries - 1:
                    time.sleep(retry_after)
                continue
            last_error = f"http_{resp.status_code}"
        except Exception as e:
            last_error = str(e)
        if attempt < retries - 1:
            time.sleep(2 ** attempt)

    return SendResult(ok=False, error=last_error)


def notify(message: str, parse_mode: str = None):
    """Best-effort notification. Tries Telegram, falls back to print."""
    if not send_telegram(message, parse_mode=parse_mode):
        log.warning("notify fallback (Telegram unavailable): %s", message)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 notify.py <message>", file=sys.stderr)
        sys.exit(1)
    notify(sys.argv[1])
