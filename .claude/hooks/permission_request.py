#!/usr/bin/env python3
"""
DQIII8 Hook — PermissionRequest v2 (autonomous 3-layer supervisor)

Layer 1 — READ_PREFIXES fast-path:
    - Read-only tools (Read, Glob, Grep, LS, WebFetch, WebSearch, TodoRead)
    - Bash commands starting with safe prefixes (ls, git log, cat, etc.)
    → auto-approves instantly without LLM

Layer 2 — LLM supervisor (openrouter tier2, timeout 3s → PERMITE):
    - Reads tasks/current_objective.txt for context
    - Responds {decision: PERMITE|REDIRIGE|ESCALA, reason}
    - PERMITE → allow | REDIRIGE → deny with suggestion | ESCALA → Layer 3

Layer 3 — Telegram escalation (10-min timeout → deny):
    - Triggered by: CRITICAL_PATTERNS in the input
    - Or when LLM supervisor says ESCALA
    - Timeout → automatic deny

If JARVIS_MODE != "autonomous" → {"decision": "allow"} always (no interference)

Input via stdin: {"tool_name": X, "tool_input": {...}, "session_id": Y, "request_id": Z}
Output via stdout: {"decision": "allow"|"deny", "reason": "..."}
"""

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

DQIII8_ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
DB = DQIII8_ROOT / "database" / "dqiii8.db"

# ── Layer 1: READ_PREFIXES ───────────────────────────────────────────────────
# Bash commands starting with these prefixes → auto-approve without LLM

READ_PREFIXES = (
    "ls",
    "find",
    "cat",
    "head",
    "tail",
    "grep",
    "wc",
    "du",
    "df",
    "echo",
    "pwd",
    "which",
    "whoami",
    "date",
    "env",
    "printenv",
    "git log",
    "git status",
    "git diff",
    "git show",
    "git branch",
    "python3 bin/",
    "python3 -c",
    "python3 -m json",
    "sqlite3",
    "ollama list",
    "ollama ps",
    "tmux ls",
    "semgrep scan",
    "black --check",
    "pip show",
    "curl -s http",
    "curl --get",
    "crontab -l",
    "systemctl status",
    "ps aux",
    "top -bn1",
    "cat /root/dqiii8/",
)

# Read-only tools → always Layer 1
READ_ONLY_TOOLS = {"Read", "Glob", "Grep", "LS", "WebFetch", "WebSearch", "TodoRead"}

# ── Layer 3: CRITICAL_PATTERNS ───────────────────────────────────────────────
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


def _is_read_prefix(command: str) -> bool:
    """Layer 1: True if Bash command starts with a safe read prefix."""
    cmd = command.strip()
    return any(cmd.startswith(prefix) for prefix in READ_PREFIXES)


def _has_critical_pattern(tool_input: dict) -> str | None:
    """Layer 3: Returns the critical pattern found, or None."""
    searchable = json.dumps(tool_input, ensure_ascii=False).lower()
    for pattern in CRITICAL_PATTERNS:
        if pattern.lower() in searchable:
            return pattern
    return None


def _read_current_objective() -> str:
    """Reads tasks/current_objective.txt for LLM supervisor context."""
    obj_file = DQIII8_ROOT / "tasks" / "current_objective.txt"
    if obj_file.exists():
        return obj_file.read_text(encoding="utf-8").strip()[:300]
    return "No objective set — general autonomous session"


def _call_llm_supervisor(tool_name: str, tool_input: dict, objective: str) -> dict:
    """
    Layer 2: Calls the LLM supervisor via openrouter_wrapper (tier2, timeout 3s).
    Returns: {"decision": "PERMITE"|"REDIRIGE"|"ESCALA", "reason": str}
    Timeout → PERMITE by default (do not block autonomy if LLM fails).
    """
    inp_summary = json.dumps(tool_input, ensure_ascii=False)[:300]
    prompt = (
        f"DQIII8 autonomous supervisor. Evaluate if this tool use aligns with the objective.\n"
        f"Objective: {objective}\n"
        f"Tool: {tool_name}\n"
        f"Input: {inp_summary}\n\n"
        f"Respond ONLY with valid JSON on one line:\n"
        f'{{"decision": "PERMITE", "reason": "brief explanation"}}\n'
        f"PERMITE = action aligns with objective, allow it\n"
        f"REDIRIGE = action doesn't align with objective, deny with suggestion\n"
        f"ESCALA = action is risky or ambiguous, needs human approval"
    )

    wrapper = DQIII8_ROOT / "bin" / "openrouter_wrapper.py"
    if not wrapper.exists():
        return {"decision": "PERMITE", "reason": "wrapper-not-found"}

    try:
        result = subprocess.run(
            ["python3", str(wrapper), "--agent", "auditor", prompt],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0 and result.stdout.strip():
            out = result.stdout.strip()
            # Extract JSON from output
            start = out.find("{")
            end = out.rfind("}") + 1
            if start != -1 and end > start:
                parsed = json.loads(out[start:end])
                if "decision" in parsed and parsed["decision"] in (
                    "PERMITE",
                    "REDIRIGE",
                    "ESCALA",
                ):
                    return parsed
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
        pass

    # Timeout or error → PERMITE (do not block autonomy on LLM failure)
    return {"decision": "PERMITE", "reason": "llm-timeout-3s"}


def _send_telegram(message: str) -> bool:
    """Layer 3: Send Telegram message. Returns True on success."""
    token = os.environ.get("DQIII8_BOT_TOKEN", "") or os.environ.get("JARVIS_BOT_TOKEN", "")
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
            except Exception:
                pass
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
    except Exception:
        pass


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
    perm_file = Path(f"/tmp/jarvis_perm_{perm_id}.json")
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
        _log_decision(session_id, tool_name, "deny", f"layer3-telegram-unavailable:{trigger_reason}", elapsed)
        _deny(f"Escalation required ({label}) — Telegram unavailable → automatic deny")
        return

    response = _poll_for_response(perm_file, start, MAX_WAIT_LAYER3_S)
    elapsed = time.time() - start

    if response is not None:
        decision = response.get("decision", "deny")
        reason = response.get("reason", "user-response")
        _log_decision(session_id, tool_name, decision, f"layer3-human:{reason}", elapsed)
        if decision == "allow":
            _allow(reason)
        else:
            _deny(reason)
    else:
        _log_decision(session_id, tool_name, "deny", f"layer3-timeout-10min:{trigger_reason}", elapsed)
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

    jarvis_mode = os.environ.get("JARVIS_MODE", "").lower()

    # Non-autonomous → always allow
    if jarvis_mode != "autonomous":
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

    # ── Layer 1: Read-only tools → fast-path ──────────────────────────────────
    if tool_name in READ_ONLY_TOOLS:
        _log_decision(session_id, tool_name, "allow", "layer1-read-only-tool", 0.0)
        _allow("layer1-read-only-tool")
        return

    # ── Layer 1: Bash with READ_PREFIXES → fast-path ──────────────────────────
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        if _is_read_prefix(command):
            _log_decision(session_id, tool_name, "allow", "layer1-read-prefix", 0.0)
            _allow("layer1-read-prefix")
            return

    # ── Layer 2: LLM supervisor for everything else ───────────────────────────
    objective = _read_current_objective()
    llm_result = _call_llm_supervisor(tool_name, tool_input, objective)
    llm_decision = llm_result.get("decision", "PERMITE")
    llm_reason = llm_result.get("reason", "")
    elapsed = time.time() - start

    if llm_decision == "ESCALA":
        # LLM requests escalation → Layer 3
        _layer3_telegram_flow(
            session_id,
            tool_name,
            tool_input,
            start,
            label="LLM supervisor ESCALA",
            trigger_reason=llm_reason,
        )
        return

    if llm_decision == "REDIRIGE":
        # Action not aligned with objective → deny with suggestion
        _log_decision(session_id, tool_name, "deny", f"layer2-redirige:{llm_reason}", elapsed)
        _deny(f"Supervisor: action not aligned with objective — {llm_reason}")
        return

    # PERMITE (or unknown) → allow
    _log_decision(session_id, tool_name, "allow", f"layer2-permite:{llm_reason}", elapsed)
    _allow("layer2-permite")


if __name__ == "__main__":
    main()
