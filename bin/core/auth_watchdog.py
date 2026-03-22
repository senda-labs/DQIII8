#!/usr/bin/env python3
"""
DQIII8 Auth Watchdog — checks Claude Code OAuth health every 30 min via cron.

Claude Code uses ~/.claude/.credentials.json (accessToken + refreshToken, auto-renewed).
Do NOT set CLAUDE_CODE_OAUTH_TOKEN — it overrides credentials and breaks auth.

Checks:
  1. ~/.claude/.credentials.json exists and has both tokens
  2. CLAUDE_CODE_OAUTH_TOKEN is NOT in the environment
  3. `claude -p "ping" --output-format json` exits 0

On failure: notifies Telegram with specific fix instructions.
On success: silent.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from notify import notify

CREDENTIALS_PATH = Path.home() / ".claude" / ".credentials.json"
_TIMEOUT = 30  # seconds


def check_credentials_file(path: Path = None) -> tuple[bool, str]:
    """Verify credentials file exists and contains both tokens."""
    target = path if path is not None else CREDENTIALS_PATH
    if not target.exists():
        return False, f"credentials file missing: {target} — run: claude /login"
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        oauth = data.get("claudeAiOauth", {})
        if not oauth.get("accessToken") or not oauth.get("refreshToken"):
            return False, "credentials file is missing accessToken or refreshToken"
        return True, ""
    except (json.JSONDecodeError, OSError) as exc:
        return False, f"cannot read credentials file: {exc}"


def check_env_conflict(env: dict = None) -> tuple[bool, str]:
    """Warn if CLAUDE_CODE_OAUTH_TOKEN is set — it overrides credentials."""
    e = env if env is not None else os.environ
    val = e.get("CLAUDE_CODE_OAUTH_TOKEN", "")
    if val:
        return False, (
            "CLAUDE_CODE_OAUTH_TOKEN is set in the environment — "
            "this overrides ~/.claude/.credentials.json and breaks auth. "
            "Fix: unset CLAUDE_CODE_OAUTH_TOKEN"
        )
    return True, ""


def check_claude_probe() -> tuple[bool, str]:
    """Probe Claude Code with a test prompt. Returns (ok, error_message)."""
    try:
        result = subprocess.run(
            ["claude", "-p", "reply with: pong", "--output-format", "json"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            encoding="utf-8",
        )
        if result.returncode == 0:
            return True, ""
        return False, (result.stderr or result.stdout).strip()
    except subprocess.TimeoutExpired:
        return False, f"claude command timeout after {_TIMEOUT}s"
    except FileNotFoundError as exc:
        return False, f"claude binary not found: {exc}"


def run_watchdog(env: dict = None) -> None:
    """Run all auth checks. Notify Telegram on any failure; silent on success."""
    # Check 1: credentials file
    ok, msg = check_credentials_file()
    if not ok:
        notify(
            "[DQIII8] Auth watchdog: credentials file problem.\n"
            f"Detail: {msg}\n\n"
            "Fix: open an interactive session and run:\n"
            "  claude /login"
        )
        return

    # Check 2: env var conflict
    ok, msg = check_env_conflict(env)
    if not ok:
        notify(
            "[DQIII8] Auth watchdog: env var conflict detected.\n"
            f"Detail: {msg}\n\n"
            "Fix: run in your shell:\n"
            "  unset CLAUDE_CODE_OAUTH_TOKEN\n"
            "And remove it from ~/.bashrc or any script that sets it."
        )
        return

    # Check 3: live probe
    ok, msg = check_claude_probe()
    if not ok:
        notify(
            "[DQIII8] Auth watchdog: claude -p probe failed.\n"
            f"Detail: {msg}\n\n"
            "Fix: open an interactive session and run:\n"
            "  claude /login\n"
            "Claude Code will refresh credentials automatically after login."
        )


if __name__ == "__main__":
    run_watchdog()
