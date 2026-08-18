#!/usr/bin/env python3
"""
DQIII8 Hook — PermissionRequest (autonomous critical-pattern escalation)

If DQIII8_MODE != "autonomous" → {"decision": "allow"} always (no interference).

In autonomous mode:
    - CRITICAL_PATTERNS in the tool input → Telegram escalation, 10-min
      timeout → automatic deny.
    - Anything else → allow (logged as "autonomous-allow-all").

INV1 (2026-08-18): this used to document a 3-layer design (READ_PREFIXES
fast-path, then an LLM supervisor call, then this escalation). Layers 1-2
were removed from main() at some earlier point ("Layer 1/2 removed: no LLM
supervisor calls in autonomous mode" — see the autonomous-mode branch below)
but the supporting code (READ_PREFIXES, READ_ONLY_TOOLS, _is_read_prefix,
_call_llm_supervisor) and this docstring were left describing the removed
design. Confirmed via grep: nothing outside this file imports any of those
names, and no test exercises them. Deleted rather than kept as fictional
documentation of dead code.

Input via stdin: {"tool_name": X, "tool_input": {...}, "session_id": Y, "request_id": Z}
Output via stdout: {"decision": "allow"|"deny", "reason": "..."}
"""

import json
import logging
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

log = logging.getLogger("dqiii8." + __name__)

DQIII8_ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
DB = DQIII8_ROOT / "database" / "dqiii8.db"

# ── CRITICAL_PATTERNS ────────────────────────────────────────────────────────
# These patterns always escalate to human (Telegram, 10-min timeout → deny)

CRITICAL_PATTERNS = [
    ".env",
    "rm -rf",
    "git push --force",
    "git push -f",
    "--force-with-lease",
    "DROP TABLE",
    "DROP DATABASE",
    "DELETE FROM agent_actions",
    "DELETE FROM instincts",
    "> /dev/sda",
    "mkfs",
    "dd if=",
    "chmod 777 /",
    ":(){:|:&};:",
]

POLL_INTERVAL_S = 5
MAX_WAIT_LAYER3_S = 600  # 10 minutes for critical actions
MAX_WAIT_TELEGRAM_S = 300  # 5 min if no Telegram config (doesn't block much)


def _allow(reason: str = "") -> None:
    print(json.dumps({"decision": "allow", "reason": reason}))


def _deny(reason: str) -> None:
    print(json.dumps({"decision": "deny", "reason": reason}))


def _has_critical_pattern(tool_input: dict) -> str | None:
    """Returns the critical pattern found, or None."""
    searchable = json.dumps(tool_input, ensure_ascii=False).lower()
    for pattern in CRITICAL_PATTERNS:
        if pattern.lower() in searchable:
            return pattern
    return None


def _send_telegram(message: str) -> bool:
    """Layer 3: Send Telegram message. Returns True on success."""
    token = os.environ.get("DQIII8_BOT_TOKEN", "") or os.environ.get(
        "JARVIS_BOT_TOKEN", ""
    )
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False
    try:
        result = subprocess.run(
            [
                "python3",
                "-c",
                f"""
import urllib.request, urllib.parse
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


def _poll_for_response(perm_file: Path, start: float, max_wait: float) -> dict | None:
    """Poll for Telegram response in perm_file. Returns dict or None on timeout."""
    while time.time() - start < max_wait:
        if perm_file.exists():
            try:
                response = json.loads(perm_file.read_text(encoding="utf-8"))
                perm_file.unlink(missing_ok=True)
                return response
            except Exception as e:
                log.debug("permission_request: perm_file poll parse failed (best-effort): %s", e)
        time.sleep(POLL_INTERVAL_S)
    return None


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
    except Exception as e:
        log.warning("permission_request: _log_decision DB write failed: %s", e, exc_info=True)


def _layer3_telegram_flow(
    session_id: str,
    tool_name: str,
    tool_input: dict,
    start: float,
    label: str,
    trigger_reason: str,
) -> None:
    """Common Layer 3 escalation flow: Telegram + 10min polling + deny on timeout."""
    perm_id = os.urandom(4).hex()
    perm_file = Path(f"/tmp/dqiii8_perm_{perm_id}.json")
    inp_summary = json.dumps(tool_input, ensure_ascii=False)[:200]

    msg = (
        f"⚠️ DQIII8 ESCALATE — {label}\n"
        f"Reason: {trigger_reason[:200]}\n"
        f"Tool: {tool_name}\n"
        f"Input: {inp_summary}\n"
        f"Session: {session_id[:8]}\n\n"
        f"/approve_{perm_id} — allow\n"
        f"/deny_{perm_id} — deny\n"
        f"(timeout: 10 min → automatic deny)"
    )

    sent = _send_telegram(msg)
    if not sent:
        elapsed = time.time() - start
        _log_decision(
            session_id,
            tool_name,
            "deny",
            f"layer3-telegram-unavailable:{trigger_reason}",
            elapsed,
        )
        _deny(f"Escalation required ({label}) — Telegram unavailable → automatic deny")
        return

    response = _poll_for_response(perm_file, start, MAX_WAIT_LAYER3_S)
    elapsed = time.time() - start

    if response is not None:
        decision = response.get("decision", "deny")
        reason = response.get("reason", "user-response")
        _log_decision(
            session_id, tool_name, decision, f"layer3-human:{reason}", elapsed
        )
        if decision == "allow":
            _allow(reason)
        else:
            _deny(reason)
    else:
        _log_decision(
            session_id,
            tool_name,
            "deny",
            f"layer3-timeout-10min:{trigger_reason}",
            elapsed,
        )
        _deny(f"Escalation {label} — 10min timeout → automatic deny")


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        _allow("parse error — defaulting to allow")
        return

    tool_name = data.get("tool_name", "")
    session_id = data.get("session_id", "unknown")
    tool_input = data.get("tool_input", {})

    dqiii8_mode = os.environ.get("DQIII8_MODE", "").lower()

    # Non-autonomous → always allow
    if dqiii8_mode != "autonomous":
        _allow()
        return

    start = time.time()

    # ── Layer 3: CRITICAL_PATTERNS — always escalate to human ─────────────────
    critical = _has_critical_pattern(tool_input)
    if critical:
        _layer3_telegram_flow(
            session_id,
            tool_name,
            tool_input,
            start,
            label="critical pattern",
            trigger_reason=f"CRITICAL_PATTERN:{critical}",
        )
        return

    # ── Autonomous mode: allow everything except CRITICAL_PATTERNS ────────────
    # Layer 1/2 removed: no LLM supervisor calls in autonomous mode.
    # Eliminates per-tool-use openrouter calls and Telegram ESCALA prompts.
    _log_decision(session_id, tool_name, "allow", "autonomous-allow-all", 0.0)
    _allow("autonomous-allow-all")


if __name__ == "__main__":
    main()
