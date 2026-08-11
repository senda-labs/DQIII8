"""Unit tests for /auth_update command in dqiii8_bot.py"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

with patch.dict(
    "sys.modules",
    {
        "telegram": MagicMock(),
        "telegram.ext": MagicMock(),
        "dotenv": MagicMock(),
        "voice_handler": MagicMock(),
    },
):
    spec = importlib.util.spec_from_file_location(
        "dqiii8_bot",
        Path(__file__).parent.parent / "bin" / "ui" / "dqiii8_bot.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)


class TestCheckCredentials:
    def test_returns_ok_when_tokens_present(self, tmp_path):
        import json

        creds = tmp_path / ".credentials.json"
        creds.write_text(
            json.dumps(
                {"claudeAiOauth": {"accessToken": "tok_a", "refreshToken": "tok_r"}}
            ),
            encoding="utf-8",
        )
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

    def test_returns_false_when_json_corrupt(self, tmp_path):
        creds = tmp_path / ".credentials.json"
        creds.write_text("not-valid-json{{{", encoding="utf-8")
        with patch.object(mod, "_CREDENTIALS_PATH", creds):
            ok, msg = mod._check_credentials()
        assert ok is False
        assert "json" in msg.lower() or "invalid" in msg.lower()


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
        creds.write_text(
            json.dumps({"claudeAiOauth": {"accessToken": "a", "refreshToken": "r"}}),
            encoding="utf-8",
        )
        update = MagicMock()
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        with patch.object(mod, "authorized", return_value=True):
            with patch.object(mod, "_CREDENTIALS_PATH", creds):
                await mod.cmd_auth_update(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "ok" in text.lower() or "valid" in text.lower()

    @pytest.mark.anyio
    async def test_replies_with_login_instructions_when_credentials_missing(
        self, tmp_path
    ):
        creds = tmp_path / "nonexistent.json"
        update = MagicMock()
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        with patch.object(mod, "authorized", return_value=True):
            with patch.object(mod, "_CREDENTIALS_PATH", creds):
                await mod.cmd_auth_update(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "claude /login" in text


def test_log_cc_command_writes_project(tmp_path, monkeypatch):
    import sqlite3

    db_path = tmp_path / "dqiii8.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE agent_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT, agent_name TEXT, tool_used TEXT, action_type TEXT,
            input_tokens INTEGER, output_tokens INTEGER, notes TEXT, project TEXT
        )
        """
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(mod, "DB", db_path)

    mod._log_cc_command(
        "/cc", "prompt text", "cc_direct", True, 42,
        session_id="test-sess", project="intl-reports",
    )

    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT project FROM agent_actions").fetchone()
    conn.close()
    assert row[0] == "intl-reports"
