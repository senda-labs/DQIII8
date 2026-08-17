"""
tests/test_wrapper_routing_guards.py — routing guard rails added 2026-07-05:

1. _NO_DOWNGRADE: Anthropic-tier (A/S) agents must never silently fall back to
   a free-tier model (audit HIGH #5).
2. Retry/backoff: transient failures retry with backoff; auth/config failures
   skip retries (audit HIGH #4).
3. Circuit breaker: N consecutive failures open the circuit; cooldown elapses →
   half-open probe; success resets.
4. Tier labeling in log_to_db inputs (nim/B+, github/B++, opus/S).
"""

import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bin.core import openrouter_wrapper as w

JARVIS = Path(__file__).resolve().parents[1]
SCHEMA_V2_SQL = (JARVIS / "database" / "schema_v2.sql").read_text(encoding="utf-8")


# ── _NO_DOWNGRADE membership ────────────────────────────────────────────────

def test_no_downgrade_covers_all_anthropic_agents():
    expected = {
        agent for agent, (prov, _m) in w.AGENT_ROUTING.items() if prov == "anthropic"
    }
    assert w._NO_DOWNGRADE == expected
    # The audit's named examples must be present
    assert {"code-reviewer", "code-validator", "auditor"} <= w._NO_DOWNGRADE


def test_build_chain_anthropic_has_no_fallback():
    chain, no_downgrade = w.build_chain(
        "anthropic", "claude-opus-4-8", allow_downgrade=False
    )
    assert no_downgrade is True
    assert chain == [("anthropic", "claude-opus-4-8")]


def test_build_chain_anthropic_optin_downgrade():
    chain, no_downgrade = w.build_chain(
        "anthropic", "claude-opus-4-8", allow_downgrade=True
    )
    assert no_downgrade is False
    assert len(chain) > 1
    assert chain[0] == ("anthropic", "claude-opus-4-8")


def test_build_chain_free_tier_keeps_fallbacks():
    chain, no_downgrade = w.build_chain("groq", "llama-3.3-70b-versatile")
    assert no_downgrade is False
    providers = [p for p, _m in chain]
    assert providers[0] == "groq"
    assert set(w.FALLBACK_CHAIN["groq"]) <= set(providers[1:])
    # No free chain may ever contain anthropic (no silent UP-escalation either)
    assert "anthropic" not in providers[1:]


def test_build_chain_ollama_escalation_appends_qwen_last_resort():
    chain, _ = w.build_chain("groq", "llama-3.3-70b-versatile",
                             escalated_from_ollama=True)
    assert chain[-1] == ("ollama", "qwen2.5-coder:7b")


# ── Retry / backoff ─────────────────────────────────────────────────────────

def _isolate_breaker(monkeypatch, tmp_path):
    monkeypatch.setattr(w, "_BREAKER_PATH", tmp_path / "breaker.json")


def test_retry_transient_then_success(monkeypatch, tmp_path):
    _isolate_breaker(monkeypatch, tmp_path)
    calls = []

    def fake_request(provider, model, prompt, system_prompt="", echo=True):
        calls.append(1)
        if len(calls) < 3:
            return "", 0, 0, False, True  # transient
        return "recovered", 1, 1, True, True

    monkeypatch.setattr(w, "_request_once", fake_request)
    monkeypatch.setattr(time, "sleep", lambda *_: None)

    text, _ti, _to, ok = w._call_with_retry("groq", "m", "p")
    assert ok is True
    assert text == "recovered"
    assert len(calls) == 3


def test_fatal_error_does_not_retry(monkeypatch, tmp_path):
    _isolate_breaker(monkeypatch, tmp_path)
    calls = []

    def fake_request(provider, model, prompt, system_prompt="", echo=True):
        calls.append(1)
        return "", 0, 0, False, False  # fatal (401/403/404)

    monkeypatch.setattr(w, "_request_once", fake_request)
    monkeypatch.setattr(time, "sleep", lambda *_: None)

    _text, _ti, _to, ok = w._call_with_retry("groq", "m", "p")
    assert ok is False
    assert len(calls) == 1


def test_retry_exhaustion_gives_up(monkeypatch, tmp_path):
    _isolate_breaker(monkeypatch, tmp_path)
    calls = []

    def fake_request(provider, model, prompt, system_prompt="", echo=True):
        calls.append(1)
        return "", 0, 0, False, True

    monkeypatch.setattr(w, "_request_once", fake_request)
    monkeypatch.setattr(time, "sleep", lambda *_: None)

    _text, _ti, _to, ok = w._call_with_retry("groq", "m", "p")
    assert ok is False
    assert len(calls) == w._RETRY_ATTEMPTS


# ── Circuit breaker ─────────────────────────────────────────────────────────

def test_breaker_opens_after_threshold_and_recovers(monkeypatch, tmp_path):
    _isolate_breaker(monkeypatch, tmp_path)

    assert w._breaker_allows("groq") is True
    for _ in range(w._BREAKER_THRESHOLD):
        w._breaker_record("groq", success=False)
    assert w._breaker_allows("groq") is False  # circuit open

    # Cooldown elapsed → half-open probe allowed
    state = w._breaker_load()
    state["groq"]["opened_until"] = time.time() - 1
    w._breaker_save(state)
    assert w._breaker_allows("groq") is True

    # Success resets the breaker completely
    w._breaker_record("groq", success=True)
    assert w._breaker_load().get("groq") is None
    assert w._breaker_allows("groq") is True


def test_breaker_open_skips_provider_without_calling(monkeypatch, tmp_path):
    _isolate_breaker(monkeypatch, tmp_path)
    for _ in range(w._BREAKER_THRESHOLD):
        w._breaker_record("nim", success=False)

    def fake_request(*a, **k):
        raise AssertionError("provider must not be called while circuit is open")

    monkeypatch.setattr(w, "_request_once", fake_request)
    _text, _ti, _to, ok = w._call_with_retry("nim", "m", "p")
    assert ok is False


def test_breaker_state_fail_open_on_corrupt_file(monkeypatch, tmp_path):
    path = tmp_path / "breaker.json"
    path.write_text("{not json")
    monkeypatch.setattr(w, "_BREAKER_PATH", path)
    assert w._breaker_allows("groq") is True


# ── stream_response compat shim ─────────────────────────────────────────────

def test_stream_response_keeps_four_tuple(monkeypatch):
    monkeypatch.setattr(
        w, "_request_once",
        lambda *a, **k: ("txt", 1, 2, True, True),
    )
    out = w.stream_response("groq", "m", "p")
    assert out == ("txt", 1, 2, True)


# ── log_to_db project parameter ─────────────────────────────────────────────

def test_log_to_db_writes_project(tmp_path, monkeypatch):
    """log_to_db()'s INSERT is exercised against the real schema_v2.sql SSOT.

    A hand-listed column subset here previously drifted behind real schema
    additions (e.g. `end_time_ms`), so the fixture silently exercised a
    schema log_to_db() never actually sees in production and its INSERT
    failed loudly (caught and logged, not raised — see fail-open DB block).
    """
    db_path = tmp_path / "dqiii8.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_V2_SQL)
    conn.commit()
    conn.close()
    monkeypatch.setattr(w, "DB_PATH", db_path)

    w.log_to_db(
        "test-agent", "test-model", "groq", 10, 20, 100, True,
        project="intl-reports",
    )

    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT project FROM agent_actions").fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "intl-reports"
