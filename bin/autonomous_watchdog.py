#!/usr/bin/env python3
"""
JARVIS — Autonomous Watchdog
Monitors autonomous-mode sessions for inactivity, time, and token limits.

Checks every 10 minutes:
  - No agent_actions in last 2h → alert + stop flag
  - Session running > 8h total → alert + stop flag
  - sessions.total_tokens > 500 000 in current session → alert + stop flag

Usage:
    python3 bin/autonomous_watchdog.py          # monitor loop
    python3 bin/autonomous_watchdog.py --test   # simulate checks without sending Telegram
"""

import os
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

JARVIS_ROOT = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB = JARVIS_ROOT / "database" / "jarvis_metrics.db"
STOP_FLAG = Path("/tmp/jarvis_autonomous_stop.flag")

CHECK_INTERVAL_S = 600  # 10 minutes
INACTIVITY_LIMIT_S = 7200  # 2 hours
SESSION_MAX_S = 28800  # 8 hours
TOKEN_LIMIT = 500_000


def _send_telegram(message: str, dry_run: bool = False) -> bool:
    if dry_run:
        print(f"[watchdog:DRY-RUN] Would send Telegram:\n{message}")
        return True
    token = os.environ.get("JARVIS_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False
    try:
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": message}).encode()
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        urllib.request.urlopen(url, data, timeout=10)
        return True
    except Exception as e:
        print(f"[watchdog] Telegram error: {e}")
        return False


def _stop(reason: str, dry_run: bool) -> None:
    msg = f"⏰ JARVIS modo sueño — {reason}"
    _send_telegram(msg, dry_run=dry_run)
    if not dry_run:
        STOP_FLAG.write_text(reason, encoding="utf-8")
        print(f"[watchdog] Stop flag written: {reason}")
    else:
        print(f"[watchdog:DRY-RUN] Would write stop flag: {reason}")
    sys.exit(0)


def _check(session_start: float, dry_run: bool) -> None:
    """Run one round of checks."""
    if not DB.exists():
        return

    try:
        conn = sqlite3.connect(str(DB), timeout=3)

        # 1. Inactivity check — last agent_action within 2h
        row = conn.execute(
            "SELECT MAX(timestamp) FROM agent_actions"
            " WHERE timestamp > datetime('now', '-2 hours')"
        ).fetchone()
        last_action = row[0] if row else None

        if last_action is None:
            # No actions in last 2h
            conn.close()
            _stop("sin actividad 2h — terminando sesión automáticamente", dry_run)
            return  # unreachable after _stop, but for dry_run

        # 2. Token limit check — current session_id (passed via env or latest open session)
        session_id = os.environ.get("CLAUDE_SESSION_ID", "")
        if session_id:
            tok_row = conn.execute(
                "SELECT total_tokens FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            if tok_row and tok_row[0] and tok_row[0] > TOKEN_LIMIT:
                conn.close()
                _stop(
                    f"límite de tokens alcanzado ({tok_row[0]:,} > {TOKEN_LIMIT:,})",
                    dry_run,
                )
                return

        conn.close()
    except Exception as e:
        print(f"[watchdog] DB check error: {e}")

    # 3. Session duration limit
    elapsed_s = time.time() - session_start
    if elapsed_s > SESSION_MAX_S:
        _stop("8h límite alcanzado", dry_run)


def main() -> None:
    dry_run = "--test" in sys.argv

    if dry_run:
        print("[watchdog] TEST MODE — no real Telegram messages or stop flags")
        # Simulate: pretend there's no activity in last 2h
        _send_telegram(
            "⏰ JARVIS modo sueño sin actividad 2h — terminando sesión automáticamente",
            dry_run=True,
        )
        print("[watchdog] Test complete.")
        return

    # Load .env for Telegram credentials
    env_file = JARVIS_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    session_start = time.time()
    pid_file = Path("/tmp/jarvis_watchdog.pid")
    pid_file.write_text(str(os.getpid()), encoding="utf-8")

    print(f"[watchdog] Started PID={os.getpid()} — checking every {CHECK_INTERVAL_S//60}min")

    while True:
        time.sleep(CHECK_INTERVAL_S)
        _check(session_start, dry_run=False)


if __name__ == "__main__":
    main()
