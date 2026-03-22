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
        ok, msg = mod.check_env_conflict({})
        assert ok is True
        assert msg == ""

    def test_returns_warning_when_var_is_set(self):
        ok, msg = mod.check_env_conflict({"CLAUDE_CODE_OAUTH_TOKEN": "sk-ant-oat01-truncated"})
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
