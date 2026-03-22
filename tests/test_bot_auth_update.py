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
        Path(__file__).parent.parent / "bin" / "ui" / "jarvis_bot.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)


class TestCheckCredentials:
    def test_returns_ok_when_tokens_present(self, tmp_path):
        import json
        creds = tmp_path / ".credentials.json"
        creds.write_text(json.dumps({
            "claudeAiOauth": {"accessToken": "tok_a", "refreshToken": "tok_r"}
        }), encoding="utf-8")
        with patch.object(mod, "_CREDENTIALS_PATH", creds):
            ok, msg = mod._check_credentials()
        assert ok is True
        assert msg == ""

    def test_returns_false_when_file_missing(self, tmp_path):
        creds = tmp_path / "nonexistent.json"
        with patch.object(mod, "_CREDENTIALS_PATH", creds):
            ok, msg = mod._check_credentials()
        assert ok is False
        assert "missing" in msg.lower()

    def test_returns_false_when_tokens_absent(self, tmp_path):
        import json
        creds = tmp_path / ".credentials.json"
        creds.write_text(json.dumps({"claudeAiOauth": {}}), encoding="utf-8")
        with patch.object(mod, "_CREDENTIALS_PATH", creds):
            ok, msg = mod._check_credentials()
        assert ok is False
        assert "token" in msg.lower() or "missing" in msg.lower()


class TestCmdAuthUpdate:
    @pytest.mark.anyio
    async def test_rejects_unauthorized(self):
        update = MagicMock()
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        with patch.object(mod, "authorized", return_value=False):
            await mod.cmd_auth_update(update, context)
        update.message.reply_text.assert_not_called()

    @pytest.mark.anyio
    async def test_replies_ok_when_credentials_valid(self, tmp_path):
        import json
        creds = tmp_path / ".credentials.json"
        creds.write_text(json.dumps({
            "claudeAiOauth": {"accessToken": "a", "refreshToken": "r"}
        }), encoding="utf-8")
        update = MagicMock()
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        with patch.object(mod, "authorized", return_value=True):
            with patch.object(mod, "_CREDENTIALS_PATH", creds):
                await mod.cmd_auth_update(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "ok" in text.lower() or "valid" in text.lower()

    @pytest.mark.anyio
    async def test_replies_with_login_instructions_when_credentials_missing(self, tmp_path):
        creds = tmp_path / "nonexistent.json"
        update = MagicMock()
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        with patch.object(mod, "authorized", return_value=True):
            with patch.object(mod, "_CREDENTIALS_PATH", creds):
                await mod.cmd_auth_update(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "claude /login" in text
