"""tests/test_dashboard_chat_persistence.py — the 5 chat call sites of dashboard.py.

Every chat call site wraps its DB access in a broad `except Exception` (or an
`if not db.exists(): return`), so a wrong/undefined path constant degrades to
"no history yet" with HTTP 200 instead of failing. A grep-only check on the
module cannot see that, and a cold import never executes these function bodies.
These tests assert a *persisted row*, which is the only thing that distinguishes
"stored" from "silently dropped".
"""

import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).parent.parent


@pytest.fixture
def chat_client(tmp_path, monkeypatch):
    (tmp_path / "database").mkdir(parents=True, exist_ok=True)
    # The chat call sites all short-circuit on `if not db.exists()`, so the file
    # has to exist before import; _persist_chat creates its own tables.
    knowledge_db = tmp_path / "database" / "dqiii8_knowledge.db"
    sqlite3.connect(str(knowledge_db)).close()

    monkeypatch.setenv("DQIII8_ROOT", str(tmp_path))
    monkeypatch.setenv("DQIII8_DASHBOARD_HOST", "127.0.0.1")

    monkeypatch.syspath_prepend(str(ROOT_DIR / "bin" / "ui"))
    monkeypatch.syspath_prepend(str(ROOT_DIR / "bin" / "core"))
    for _mod_name in ("dashboard", "db", "dashboard_security"):
        sys.modules.pop(_mod_name, None)
    import dashboard as dash_module

    token = dash_module.get_or_create_dashboard_token()
    with TestClient(dash_module.app, headers={"Authorization": f"Bearer {token}"}) as tc:
        yield tc, dash_module, knowledge_db

    # Same rationale as tests/test_dashboard_production.py: these modules cache
    # their DB path from DQIII8_ROOT at import time, so leaving them in
    # sys.modules poisons every later import with a tmp_path that is gone.
    for _mod_name in ("dashboard", "db", "dashboard_security"):
        sys.modules.pop(_mod_name, None)


def _rows(db_path: Path, sql: str, args: tuple = ()) -> list:
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


def test_persist_chat_writes_rows_to_the_knowledge_db(chat_client):
    _, dash, knowledge_db = chat_client
    dash._persist_chat("sess-a", "pregunta uno", "respuesta uno")

    sessions = _rows(knowledge_db, "SELECT session_id FROM chat_sessions")
    messages = _rows(
        knowledge_db,
        "SELECT role, content FROM chat_messages WHERE session_id = ? ORDER BY id",
        ("sess-a",),
    )
    assert [r[0] for r in sessions] == ["sess-a"]
    assert messages == [("user", "pregunta uno"), ("assistant", "respuesta uno")]


def test_chat_history_returns_the_persisted_session(chat_client):
    tc, dash, _ = chat_client
    dash._persist_chat("sess-b", "hola mundo", "respuesta")

    resp = tc.get("/api/chat/history")
    assert resp.status_code == 200
    assert [s["id"] for s in resp.json()] == ["sess-b"]


def test_chat_search_finds_the_persisted_content(chat_client):
    tc, dash, _ = chat_client
    dash._persist_chat("sess-c", "buscame por wolframio", "respuesta")

    resp = tc.get("/api/chat/search", params={"q": "wolframio"})
    assert resp.status_code == 200
    assert [s["id"] for s in resp.json()] == ["sess-c"]


def test_chat_session_messages_returns_both_turns(chat_client):
    tc, dash, _ = chat_client
    dash._persist_chat("sess-d", "pregunta", "respuesta")

    resp = tc.get("/api/chat/sess-d/messages")
    assert resp.status_code == 200
    assert [(m["role"], m["content"]) for m in resp.json()] == [
        ("user", "pregunta"),
        ("assistant", "respuesta"),
    ]


def test_delete_chat_session_removes_the_rows(chat_client):
    tc, dash, knowledge_db = chat_client
    dash._persist_chat("sess-e", "pregunta", "respuesta")

    resp = tc.post("/api/chat/sess-e/delete")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    assert _rows(knowledge_db, "SELECT 1 FROM chat_sessions") == []
    assert _rows(knowledge_db, "SELECT 1 FROM chat_messages") == []


def test_chat_calls_never_touch_the_live_db(chat_client):
    """The whole point of the rename: chat must not reach dqiii8.db."""
    _, dash, _ = chat_client
    dash._persist_chat("sess-f", "pregunta", "respuesta")

    live_db = Path(dash.ROOT_DIR) / "database" / "dqiii8.db"
    if live_db.exists():
        assert (
            _rows(live_db, "SELECT COUNT(*) FROM sqlite_master WHERE name='chat_messages'")[0][0]
            == 0
        )
