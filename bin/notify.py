#!/usr/bin/env python3
"""Notification utilities for DQIII8. Uses direct API calls to avoid bot daemon conflicts."""
import os
import sys

import requests


def send_telegram(message: str, parse_mode: str = None) -> bool:
    """Send a message via Telegram API directly (no bot daemon needed)."""
    token = os.environ.get("DQIII8_BOT_TOKEN", "") or os.environ.get("TELEGRAM_BOT_TOKEN", "") or os.environ.get("JARVIS_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        return False

    try:
        payload = {"chat_id": chat_id, "text": message[:4096]}
        if parse_mode:
            payload["parse_mode"] = parse_mode

        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json=payload,
            timeout=10,
        )
        return resp.status_code == 200
    except Exception:
        return False


def notify(message: str, parse_mode: str = None):
    """Best-effort notification. Tries Telegram, falls back to print."""
    if not send_telegram(message, parse_mode=parse_mode):
        print(f"[notify] {message}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 notify.py <message>", file=sys.stderr)
        sys.exit(1)
    notify(sys.argv[1])
