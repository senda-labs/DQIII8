#!/usr/bin/env python3
"""
JARVIS Hook — PermissionRequest (Modo Sueño)
Handles tool permission decisions for autonomous mode.

If JARVIS_MODE=autonomous:
  - SAFE_AUTO_APPROVE tools → {"decision": "allow"} immediately
  - Other tools → send Telegram notification + poll for response (5 min timeout)
  - Timeout → {"decision": "deny", "reason": "timeout 5min"}

If not autonomous → {"decision": "allow"} (no interference)

Input via stdin: {"tool_name": X, "tool_input": {...}, "session_id": Y, "request_id": Z}
Output via stdout: {"decision": "allow"|"deny", "reason": "..."}
"""

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

JARVIS_ROOT = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB = JARVIS_ROOT / "database" / "jarvis_metrics.db"

SAFE_AUTO_APPROVE = {
    "Read",
    "Glob",
    "Grep",
    "LS",
    "Write",
    "Edit",
    "MultiEdit",
    "Bash",
    "WebFetch",
    "WebSearch",
    "TodoRead",
    "TodoWrite",
}

POLL_INTERVAL_S = 5
MAX_WAIT_S = 300  # 5 minutes


def _allow(reason: str = "") -> None:
    print(json.dumps({"decision": "allow", "reason": reason}))


def _deny(reason: str) -> None:
    print(json.dumps({"decision": "deny", "reason": reason}))


def _send_telegram(message: str) -> bool:
    """Send Telegram message via jarvis_bot pattern (subprocess to avoid import overhead)."""
    import subprocess

    token = os.environ.get("JARVIS_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False

    try:
        result = subprocess.run(
            [
                "python3",
                "-c",
                f"""
import urllib.request, urllib.parse, json
url = "https://api.telegram.org/bot{token}/sendMessage"
data = urllib.parse.urlencode({{"chat_id": "{chat_id}", "text": {repr(message)}}}).encode()
urllib.request.urlopen(url, data, timeout=10)
""",
            ],
            capture_output=True,
            timeout=15,
        )
        return result.returncode == 0
    except Exception:
        return False


def _log_decision(
    session_id: str,
    tool_name: str,
    decision: str,
    reason: str,
    response_time_s: float,
) -> None:
    if not DB.exists():
        return
    try:
        conn = sqlite3.connect(str(DB), timeout=2)
        conn.execute(
            "INSERT INTO permission_decisions "
            "(session_id, tool_name, decision, reason, response_time_s) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, tool_name, decision, reason, response_time_s),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        _allow("parse error — defaulting to allow")
        return

    tool_name = data.get("tool_name", "")
    session_id = data.get("session_id", "unknown")
    request_id = data.get("request_id", "")
    tool_input = data.get("tool_input", {})

    jarvis_mode = os.environ.get("JARVIS_MODE", "").lower()

    # Not autonomous → always allow
    if jarvis_mode != "autonomous":
        _allow()
        return

    # Safe tools → auto-approve
    if tool_name in SAFE_AUTO_APPROVE:
        _log_decision(session_id, tool_name, "allow", "safe-auto-approve", 0.0)
        _allow("safe-auto-approve")
        return

    # Unsafe tool → request Telegram approval
    perm_id = os.urandom(4).hex()  # 8 hex chars
    perm_file = Path(f"/tmp/jarvis_perm_{perm_id}.json")

    # Build context summary for the message
    inp_summary = json.dumps(tool_input, ensure_ascii=False)[:200]
    msg = (
        f"JARVIS necesita permiso\n"
        f"Tool: {tool_name}\n"
        f"Input: {inp_summary}\n"
        f"Session: {session_id[:8]}\n\n"
        f"/aprobar_{perm_id} — allow\n"
        f"/denegar_{perm_id} — deny"
    )

    sent = _send_telegram(msg)
    if not sent:
        # No Telegram → auto-deny unsafe ops in autonomous mode without oversight
        _log_decision(session_id, tool_name, "deny", "telegram-unavailable", 0.0)
        _deny("telegram unavailable — cannot request approval for unsafe tool")
        return

    # Poll for response
    start = time.time()
    while time.time() - start < MAX_WAIT_S:
        if perm_file.exists():
            try:
                response = json.loads(perm_file.read_text(encoding="utf-8"))
                perm_file.unlink(missing_ok=True)
                decision = response.get("decision", "deny")
                reason = response.get("reason", "user-response")
                elapsed = time.time() - start
                _log_decision(session_id, tool_name, decision, reason, elapsed)
                if decision == "allow":
                    _allow(reason)
                else:
                    _deny(reason)
                return
            except Exception:
                pass
        time.sleep(POLL_INTERVAL_S)

    # Timeout
    elapsed = time.time() - start
    _log_decision(session_id, tool_name, "deny", "timeout 5min", elapsed)
    _deny("timeout 5min — no response received")


if __name__ == "__main__":
    main()
