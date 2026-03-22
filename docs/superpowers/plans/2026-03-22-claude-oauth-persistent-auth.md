# Claude Code OAuth Persistent Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure Claude Code OAuth authentication persists across VPS sessions without manual re-login, using Claude Code's native credential management.

**Architecture:** Claude Code auto-manages `~/.claude/.credentials.json` (accessToken + refreshToken with auto-renewal). The ONLY thing that breaks auth is if `CLAUDE_CODE_OAUTH_TOKEN` is set in the environment — it overrides (and corrupts) the credential lookup. Solution: ensure that variable is never set. Auth watchdog checks both credentials presence and absence of the conflicting env var, then probes with `claude -p`. On failure it instructs the user to run `claude /login` interactively.

**IMPORTANT — What NOT to do:**
- Do NOT create `/root/.claude-env` or any file with `CLAUDE_CODE_OAUTH_TOKEN=...`
- Do NOT set `CLAUDE_CODE_OAUTH_TOKEN` in `.bashrc`, `.env`, or any script
- Do NOT call `claude setup-token` — that produces truncated tokens that break auth

**Tech Stack:** bash, Python 3.11, subprocess, python-telegram-bot>=20, cron, unittest.mock

---

## Status

| Task | Type | Status |
|------|------|--------|
| Pre-condition | Manual (local) | ✅ DONE — credentials active via `claude /login` |
| Task 1 | Manual (VPS) | Pending |
| Task 2 | Subagent | Pending |
| Task 3 | Manual verification | ✅ DONE — `claude -p "pong"` returns pong |
| Task 4 | Subagent (TDD) | Pending |
| Task 5 | Subagent | ✅ DONE — crontab every 30 min, silent exit 0 |
| Task 6 | Subagent (TDD) | Pending |

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Verify (manual) | `~/.claude/.credentials.json` | Must exist with accessToken + refreshToken |
| Modify (manual) | `~/.bashrc` | Add `unset CLAUDE_CODE_OAUTH_TOKEN` |
| Modify | `bin/autonomous_loop.sh` | Add `unset CLAUDE_CODE_OAUTH_TOKEN` guard |
| Create | `bin/core/auth_watchdog.py` | Check credentials + health probe + Telegram alert |
| Create | `tests/test_auth_watchdog.py` | Unit tests for watchdog |
| Modify | `bin/ui/jarvis_bot.py` | Add `cmd_auth_update` + `CommandHandler` |
| Create | `tests/test_bot_auth_update.py` | Unit tests for bot command |

---

## Task 1: Verify credentials + prevent env var conflict (manual, VPS)

**Files:**
- Verify: `~/.claude/.credentials.json`
- Modify: `~/.bashrc`

- [ ] **Step 1.1: Verify credentials file exists and has required fields**

```bash
python3 -c "
import json
from pathlib import Path
creds = Path.home() / '.claude' / '.credentials.json'
if not creds.exists():
    print('ERROR: credentials file missing — run: claude /login')
else:
    data = json.loads(creds.read_text())
    has_access = bool(data.get('claudeAiOauth', {}).get('accessToken', ''))
    has_refresh = bool(data.get('claudeAiOauth', {}).get('refreshToken', ''))
    print(f'accessToken:  {\"OK\" if has_access else \"MISSING\"}')
    print(f'refreshToken: {\"OK\" if has_refresh else \"MISSING\"}')
"
# Expected: accessToken: OK / refreshToken: OK
```

- [ ] **Step 1.2: Ensure CLAUDE_CODE_OAUTH_TOKEN is NOT set anywhere**

```bash
# Check current env
echo "Current value: '${CLAUDE_CODE_OAUTH_TOKEN:-<not set>}'"

# Check .bashrc / .bash_profile / .profile for the variable
grep -r 'CLAUDE_CODE_OAUTH_TOKEN' ~/.bashrc ~/.bash_profile ~/.profile ~/.env /root/jarvis/.env 2>/dev/null && echo "FOUND — must remove" || echo "Not found — OK"
```

- [ ] **Step 1.3: Add unset guard to ~/.bashrc**

```bash
# Prevent any accidental CLAUDE_CODE_OAUTH_TOKEN from a parent process or future mistake
grep -q 'CLAUDE_CODE_OAUTH_TOKEN' ~/.bashrc || \
    echo '# Prevent this var from overriding ~/.claude/.credentials.json' >> ~/.bashrc && \
    echo 'unset CLAUDE_CODE_OAUTH_TOKEN' >> ~/.bashrc

source ~/.bashrc
echo "Var after source: '${CLAUDE_CODE_OAUTH_TOKEN:-<not set>}'"
# Expected: <not set>
```

---

## Task 2: Add unset guard in autonomous_loop.sh

**Files:**
- Modify: `bin/autonomous_loop.sh` (after line 14, `export JARVIS_ROOT=...`)

- [ ] **Step 2.1: Add unset line after the initial exports**

The top of the file should become:

```bash
set -euo pipefail

export JARVIS_MODE=autonomous
export JARVIS_ROOT=/root/jarvis

# Prevent CLAUDE_CODE_OAUTH_TOKEN from overriding ~/.claude/.credentials.json
# Claude Code uses credentials.json with auto-renewal — env var breaks auth
unset CLAUDE_CODE_OAUTH_TOKEN
```

- [ ] **Step 2.2: Verify no syntax errors**

```bash
bash -n bin/autonomous_loop.sh
# Expected: no output
```

- [ ] **Step 2.3: Commit**

```bash
git add bin/autonomous_loop.sh
git commit -m "fix: unset CLAUDE_CODE_OAUTH_TOKEN in autonomous_loop to prevent auth conflict

Claude Code uses ~/.claude/.credentials.json for OAuth (auto-renewed).
Setting CLAUDE_CODE_OAUTH_TOKEN in env overrides the credentials lookup
and breaks auth with a truncated/invalid token.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: Implement auth_watchdog.py (TDD)

**Files:**
- Create: `tests/test_auth_watchdog.py`
- Create: `bin/core/auth_watchdog.py`

### 4a — Write failing tests first

- [ ] **Step 4.1: Write test file**

```python
# tests/test_auth_watchdog.py
"""Unit tests for bin/core/auth_watchdog.py"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

spec = importlib.util.spec_from_file_location(
    "auth_watchdog",
    Path("/root/jarvis/bin/core/auth_watchdog.py"),
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TestCheckCredentialsFile:
    def test_returns_ok_when_file_has_tokens(self, tmp_path):
        creds = tmp_path / ".credentials.json"
        creds.write_text(json.dumps({
            "claudeAiOauth": {
                "accessToken": "tok_access",
                "refreshToken": "tok_refresh",
            }
        }), encoding="utf-8")
        ok, msg = mod.check_credentials_file(creds)
        assert ok is True
        assert msg == ""

    def test_returns_error_when_file_missing(self, tmp_path):
        creds = tmp_path / ".credentials.json"
        ok, msg = mod.check_credentials_file(creds)
        assert ok is False
        assert "missing" in msg.lower() or "not found" in msg.lower()

    def test_returns_error_when_tokens_empty(self, tmp_path):
        creds = tmp_path / ".credentials.json"
        creds.write_text(json.dumps({"claudeAiOauth": {}}), encoding="utf-8")
        ok, msg = mod.check_credentials_file(creds)
        assert ok is False
        assert "token" in msg.lower()


class TestCheckEnvConflict:
    def test_returns_ok_when_var_not_set(self):
        env = {}
        ok, msg = mod.check_env_conflict(env)
        assert ok is True
        assert msg == ""

    def test_returns_warning_when_var_is_set(self):
        env = {"CLAUDE_CODE_OAUTH_TOKEN": "sk-ant-oat01-truncated"}
        ok, msg = mod.check_env_conflict(env)
        assert ok is False
        assert "CLAUDE_CODE_OAUTH_TOKEN" in msg


class TestCheckClaudeProbe:
    def test_returns_true_on_zero_exit(self):
        mock_result = MagicMock(returncode=0, stdout='{"result":"pong"}', stderr="")
        with patch("subprocess.run", return_value=mock_result):
            ok, msg = mod.check_claude_probe()
        assert ok is True
        assert msg == ""

    def test_calls_with_output_format_json(self):
        mock_result = MagicMock(returncode=0, stdout="{}", stderr="")
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            mod.check_claude_probe()
        args = mock_run.call_args[0][0]
        assert "--output-format" in args and "json" in args

    def test_returns_false_on_nonzero_exit(self):
        mock_result = MagicMock(returncode=1, stdout="", stderr="401 Unauthorized")
        with patch("subprocess.run", return_value=mock_result):
            ok, msg = mod.check_claude_probe()
        assert ok is False

    def test_returns_false_on_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("claude", 30)):
            ok, msg = mod.check_claude_probe()
        assert ok is False
        assert "timeout" in msg.lower()


class TestRunWatchdog:
    def test_silent_when_all_checks_pass(self, tmp_path):
        creds = tmp_path / ".credentials.json"
        creds.write_text(json.dumps({
            "claudeAiOauth": {"accessToken": "tok", "refreshToken": "ref"}
        }), encoding="utf-8")
        with patch.object(mod, "CREDENTIALS_PATH", creds):
            with patch.object(mod, "check_claude_probe", return_value=(True, "")):
                with patch.object(mod, "notify") as mock_notify:
                    mod.run_watchdog(env={})
        mock_notify.assert_not_called()

    def test_notifies_on_missing_credentials(self, tmp_path):
        creds = tmp_path / ".credentials.json"  # does not exist
        with patch.object(mod, "CREDENTIALS_PATH", creds):
            with patch.object(mod, "notify") as mock_notify:
                mod.run_watchdog(env={})
        mock_notify.assert_called_once()
        text = mock_notify.call_args[0][0]
        assert "claude /login" in text

    def test_notifies_on_env_conflict(self, tmp_path):
        creds = tmp_path / ".credentials.json"
        creds.write_text(json.dumps({
            "claudeAiOauth": {"accessToken": "tok", "refreshToken": "ref"}
        }), encoding="utf-8")
        with patch.object(mod, "CREDENTIALS_PATH", creds):
            with patch.object(mod, "check_claude_probe", return_value=(True, "")):
                with patch.object(mod, "notify") as mock_notify:
                    mod.run_watchdog(env={"CLAUDE_CODE_OAUTH_TOKEN": "bad"})
        mock_notify.assert_called_once()
        text = mock_notify.call_args[0][0]
        assert "CLAUDE_CODE_OAUTH_TOKEN" in text
        assert "unset" in text

    def test_notifies_on_probe_failure(self, tmp_path):
        creds = tmp_path / ".credentials.json"
        creds.write_text(json.dumps({
            "claudeAiOauth": {"accessToken": "tok", "refreshToken": "ref"}
        }), encoding="utf-8")
        with patch.object(mod, "CREDENTIALS_PATH", creds):
            with patch.object(mod, "check_claude_probe", return_value=(False, "401")):
                with patch.object(mod, "notify") as mock_notify:
                    mod.run_watchdog(env={})
        mock_notify.assert_called_once()
        text = mock_notify.call_args[0][0]
        assert "claude /login" in text
```

- [ ] **Step 4.2: Run tests — verify they FAIL**

```bash
cd /root/jarvis
python -m pytest tests/test_auth_watchdog.py -v 2>&1 | head -20
# Expected: ModuleNotFoundError — file doesn't exist yet
```

### 4b — Implement the watchdog

- [ ] **Step 4.3: Create bin/core/auth_watchdog.py**

```python
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
        return False, f"claude command timed out after {_TIMEOUT}s"
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
```

- [ ] **Step 4.4: Run tests — verify they PASS**

```bash
python -m pytest tests/test_auth_watchdog.py -v
# Expected: all passed
```

- [ ] **Step 4.5: Commit**

```bash
git add bin/core/auth_watchdog.py tests/test_auth_watchdog.py
git commit -m "feat: add auth_watchdog — credentials health check + Telegram alert

Checks: credentials.json exists, CLAUDE_CODE_OAUTH_TOKEN absent, probe ok.
On failure: Telegram alert with claude /login instructions.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5: Configure crontab for watchdog

- [ ] **Step 5.1: Ensure log directory exists**

```bash
mkdir -p /root/jarvis/database/audit_reports
```

- [ ] **Step 5.2: Add cron entry**

```bash
(crontab -l 2>/dev/null; echo "*/30 * * * * JARVIS_ROOT=/root/jarvis /usr/bin/python3 /root/jarvis/bin/core/auth_watchdog.py >> /root/jarvis/database/audit_reports/auth_watchdog.log 2>&1") | crontab -
```

- [ ] **Step 5.3: Verify cron entry**

```bash
crontab -l | grep auth_watchdog
# Expected: */30 * * * * JARVIS_ROOT=... auth_watchdog.py ...
```

- [ ] **Step 5.4: Test manual run**

```bash
JARVIS_ROOT=/root/jarvis python3 /root/jarvis/bin/core/auth_watchdog.py
echo "Exit: $?"
# Expected: exit 0, no output, no Telegram notification
```

---

## Task 6: Add /auth_update command to jarvis_bot.py (TDD)

> Note: With the new architecture, `/auth_update` serves as an emergency fallback
> (e.g., writing a valid token if credentials.json is lost/corrupted). It validates
> the token format before writing to prevent the truncated-token problem.

**Files:**
- Create: `tests/test_bot_auth_update.py`
- Modify: `bin/ui/jarvis_bot.py`

### 6a — Write failing tests first

- [ ] **Step 6.1: Write test file**

```python
# tests/test_bot_auth_update.py
"""Unit tests for /auth_update command in jarvis_bot.py"""
import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

with patch.dict("sys.modules", {
    "telegram": MagicMock(),
    "telegram.ext": MagicMock(),
    "dotenv": MagicMock(),
    "voice_handler": MagicMock(),
}):
    spec = importlib.util.spec_from_file_location(
        "jarvis_bot",
        Path("/root/jarvis/bin/ui/jarvis_bot.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)


class TestCmdAuthUpdate:
    @pytest.mark.asyncio
    async def test_rejects_empty_args(self):
        update = MagicMock()
        update.effective_chat.id = "123"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.args = []
        with patch.object(mod, "authorized", return_value=True):
            await mod.cmd_auth_update(update, context)
        call_text = update.message.reply_text.call_args[0][0].lower()
        assert "usage" in call_text or "/login" in call_text

    @pytest.mark.asyncio
    async def test_rejects_unauthorized(self):
        update = MagicMock()
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.args = ["whatever"]
        with patch.object(mod, "authorized", return_value=False):
            await mod.cmd_auth_update(update, context)
        update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_args_shows_auth_status(self):
        """With no args, show current auth status (credentials.json check)."""
        update = MagicMock()
        update.effective_chat.id = "123"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.args = []
        with patch.object(mod, "authorized", return_value=True):
            await mod.cmd_auth_update(update, context)
        update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_status_check_reports_credentials_missing(self):
        """When credentials.json is absent, reply includes fix instructions."""
        update = MagicMock()
        update.effective_chat.id = "123"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.args = []
        with patch.object(mod, "authorized", return_value=True):
            with patch.object(mod, "_check_credentials", return_value=(False, "credentials missing")):
                await mod.cmd_auth_update(update, context)
        call_text = update.message.reply_text.call_args[0][0]
        assert "login" in call_text.lower() or "credentials" in call_text.lower()

    @pytest.mark.asyncio
    async def test_status_check_ok_shows_healthy(self):
        """When credentials are OK, reply confirms healthy status."""
        update = MagicMock()
        update.effective_chat.id = "123"
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.args = []
        with patch.object(mod, "authorized", return_value=True):
            with patch.object(mod, "_check_credentials", return_value=(True, "")):
                await mod.cmd_auth_update(update, context)
        call_text = update.message.reply_text.call_args[0][0].lower()
        assert "ok" in call_text or "valid" in call_text or "credentials" in call_text
```

- [ ] **Step 6.2: Run tests — verify they FAIL**

```bash
python -m pytest tests/test_bot_auth_update.py -v 2>&1 | head -20
# Expected: AttributeError — cmd_auth_update / _check_credentials don't exist
```

### 6b — Implement the command

- [ ] **Step 6.3: Add helper + handler to jarvis_bot.py**

Add after the `VOICE_RESPONSES_ENABLED` line (around line 73):

```python
def _check_credentials() -> tuple[bool, str]:
    """Check ~/.claude/.credentials.json for required OAuth tokens."""
    import json as _json
    creds = Path.home() / ".claude" / ".credentials.json"
    if not creds.exists():
        return False, "credentials file missing"
    try:
        data = _json.loads(creds.read_text(encoding="utf-8"))
        oauth = data.get("claudeAiOauth", {})
        if not oauth.get("accessToken") or not oauth.get("refreshToken"):
            return False, "accessToken or refreshToken missing"
        return True, ""
    except Exception as exc:
        return False, str(exc)
```

Add immediately before `def main()`:

```python
async def cmd_auth_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check Claude Code OAuth credentials status.

    Usage: /auth_update
    Reports whether ~/.claude/.credentials.json is healthy.
    If broken: instructions to run `claude /login` in an interactive session.
    """
    if not authorized(update):
        return
    ok, msg = _check_credentials()
    if ok:
        await update.message.reply_text(
            "Credentials OK — ~/.claude/.credentials.json has valid tokens.\n"
            "Claude Code will auto-renew them as needed."
        )
    else:
        await update.message.reply_text(
            f"Credentials problem: {msg}\n\n"
            "Fix: open an SSH session to the VPS and run:\n"
            "  claude /login\n"
            "Then follow the browser OAuth flow."
        )
    log.info("Auth status checked via /auth_update: ok=%s", ok)
```

- [ ] **Step 6.4: Register handler in main()**

Add before the `MessageHandler(filters.Regex(...))` lines:

```python
APP.add_handler(CommandHandler("auth_update", cmd_auth_update))
```

- [ ] **Step 6.5: Run tests**

```bash
python -m pytest tests/test_bot_auth_update.py -v
# Expected: all passed
```

- [ ] **Step 6.6: Run full suite — no regressions**

```bash
python -m pytest tests/ -v --timeout=30 2>&1 | tail -20
```

- [ ] **Step 6.7: Commit**

```bash
git add bin/ui/jarvis_bot.py tests/test_bot_auth_update.py
git commit -m "feat: add /auth_update command — checks OAuth credentials health

Reports status of ~/.claude/.credentials.json and gives fix instructions
if credentials are missing or incomplete (run claude /login).

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Final Verification Checklist

- [ ] `~/.claude/.credentials.json` exists with accessToken + refreshToken
- [ ] `CLAUDE_CODE_OAUTH_TOKEN` is NOT set in any shell or script
- [ ] `bash -n bin/autonomous_loop.sh` passes
- [ ] `claude -p "reply: pong" --output-format json` returns JSON
- [ ] `python -m pytest tests/test_auth_watchdog.py tests/test_bot_auth_update.py -v` all pass
- [ ] `crontab -l | grep auth_watchdog` shows the entry
- [ ] Send `/auth_update` from Telegram — bot reports credentials status

---

## Security Notes

- No tokens stored in files or env vars — Claude Code handles this natively
- `~/.claude/.credentials.json` is managed exclusively by Claude Code
- Bot command is read-only (checks status, never writes credentials)
- Only authorized `TELEGRAM_CHAT_ID` can call bot commands
