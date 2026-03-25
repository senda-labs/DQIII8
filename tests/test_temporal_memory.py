"""
Tests for bin/agents/temporal_memory.py and bin/agents/vector_store.py
Bloque 9 — Temporal Memory + sqlite-vec

Run: python3 -m pytest tests/test_temporal_memory.py -v
"""

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

# Point to test DB so we don't pollute dqiii8.db
_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB.close()
os.environ["DQIII8_ROOT"] = str(Path(_TMP_DB.name).parent)

# Monkeypatch DB_PATH before importing
import importlib

# We'll directly patch the DB path on the modules after import
sys.path.insert(0, str(Path(__file__).parent.parent / "bin" / "agents"))

import temporal_memory as tm
import vector_store as vs

# Redirect both modules to the temp DB
_TMP_PATH = Path(_TMP_DB.name)
tm.DB_PATH = _TMP_PATH
vs.DB_PATH = _TMP_PATH

# Apply schema to the temp DB
_SCHEMA = Path(__file__).parent.parent / "database" / "schema_temporal.sql"


@pytest.fixture(autouse=True)
def _fresh_db():
    """Re-create schema in temp DB before each test."""
    conn = sqlite3.connect(str(_TMP_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    schema_sql = _SCHEMA.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.close()
    yield
    # Drop all temporal tables after each test for isolation
    conn = sqlite3.connect(str(_TMP_PATH))
    for table in ("fact_access_log", "facts", "relations", "episodes", "vector_chunks"):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.commit()
    conn.close()


# ── Test 1: add_fact and temporal supersession ─────────────────────────────────


def test_fact_supersession():
    """Adding a new fact for (entity, predicate, domain) invalidates the old one."""
    ep = tm.add_episode("sess-1", "test-agent", "Test episode", "test")
    f1 = tm.add_fact("python", "version", "3.10", domain="test", source_episode_id=ep)
    f2 = tm.add_fact("python", "version", "3.12", domain="test", source_episode_id=ep)

    # Only f2 should be active
    active = tm.query_facts("python", "version", "test")
    assert len(active) == 1
    assert active[0]["value"] == "3.12"
    assert active[0]["id"] == f2

    # f1 should be expired (valid_until IS NOT NULL)
    all_facts = tm.query_facts("python", "version", "test", include_expired=True)
    assert len(all_facts) == 2
    expired = [f for f in all_facts if f["id"] == f1]
    assert expired[0]["valid_until"] is not None
    assert expired[0]["invalidated_by"] == f2


# ── Test 2: query_facts with as_of filter ─────────────────────────────────────


def test_query_facts_as_of():
    """query_facts with as_of returns the fact valid at that timestamp."""
    import time

    ep = tm.add_episode("sess-2", "agent", "", "test")
    f1 = tm.add_fact("model", "tier", "gpt-3", domain="test", source_episode_id=ep)

    snapshot_time = tm._now_iso()
    time.sleep(1.1)  # cross a 1-second boundary so timestamps are distinct

    f2 = tm.add_fact("model", "tier", "gpt-4", domain="test", source_episode_id=ep)

    # At snapshot_time, f1 should be the active fact
    at_snapshot = tm.query_facts("model", "tier", "test", as_of=snapshot_time)
    assert len(at_snapshot) == 1
    assert at_snapshot[0]["value"] == "gpt-3"

    # Currently, only f2 is active
    current = tm.query_facts("model", "tier", "test")
    assert current[0]["value"] == "gpt-4"


# ── Test 3: search_facts text search ──────────────────────────────────────────


def test_search_facts_text():
    """search_facts returns active facts matching query terms."""
    ep = tm.add_episode("sess-3", "agent", "", "finance")
    tm.add_fact(
        "WACC",
        "formula",
        "Ke*E/V + Kd*D/V*(1-T)",
        domain="finance",
        source_episode_id=ep,
    )
    tm.add_fact(
        "DCF",
        "method",
        "discounted cash flow valuation",
        domain="finance",
        source_episode_id=ep,
    )
    tm.add_fact(
        "EPS",
        "definition",
        "earnings per share metric",
        domain="finance",
        source_episode_id=ep,
    )

    results = tm.search_facts("cash flow", top_k=5, domain="finance")
    assert len(results) >= 1
    values = [r["value"] for r in results]
    assert any("cash flow" in v.lower() for v in values)

    # Domain filter: "python" domain should return nothing
    results_filtered = tm.search_facts("cash flow", top_k=5, domain="python")
    assert len(results_filtered) == 0


# ── Test 4: add_relation and query_relations ───────────────────────────────────


def test_add_and_query_relation():
    """add_relation stores a directed edge; query_relations retrieves it."""
    ep = tm.add_episode("sess-4", "agent", "", "science")
    rel_id = tm.add_relation(
        "python",
        "is_a",
        "programming_language",
        domain="science",
        source_episode_id=ep,
        confidence=0.99,
    )
    assert isinstance(rel_id, int) and rel_id > 0

    # Query by subject
    rels = tm.query_relations(subject="python", domain="science")
    assert len(rels) == 1
    assert rels[0]["object"] == "programming_language"
    assert rels[0]["predicate"] == "is_a"
    assert abs(rels[0]["confidence"] - 0.99) < 1e-6

    # Query by object
    rels_by_obj = tm.query_relations(object_="programming_language")
    assert len(rels_by_obj) == 1

    # Query for non-existent relation
    rels_none = tm.query_relations(subject="python", predicate="is_not")
    assert len(rels_none) == 0


# ── Test 5: add_episode and fact_access_log ────────────────────────────────────


def test_episode_and_access_log():
    """Episodes link facts; fact_access_log tracks queries when session_id given."""
    ep = tm.add_episode("sess-5", "test-agent", "Access log test", "meta")
    f1 = tm.add_fact("agent", "status", "active", domain="meta", source_episode_id=ep)
    f2 = tm.add_fact(
        "agent", "model", "sonnet-4-6", domain="meta", source_episode_id=ep
    )

    # query_facts with session_id should log accesses
    results = tm.query_facts(domain="meta", session_id="sess-5")
    assert len(results) == 2

    conn = sqlite3.connect(str(_TMP_PATH))
    logged = conn.execute(
        "SELECT COUNT(*) FROM fact_access_log WHERE session_id = 'sess-5'"
    ).fetchone()[0]
    conn.close()
    assert logged == 2

    # Verify episode metadata using row_factory
    conn = sqlite3.connect(str(_TMP_PATH))
    conn.row_factory = sqlite3.Row
    ep_row = conn.execute("SELECT * FROM episodes WHERE id = ?", (ep,)).fetchone()
    conn.close()
    assert ep_row is not None
    assert ep_row["agent_name"] == "test-agent"
    assert ep_row["domain"] == "meta"


# ── Test 6: vector_store — init and upsert ────────────────────────────────────


def test_vector_store_init_and_upsert():
    """vec0 table can be created and vectors inserted/searched."""
    # Ensure schema is applied
    conn = sqlite3.connect(str(_TMP_PATH))
    conn.executescript(
        (Path(__file__).parent.parent / "database" / "schema_temporal.sql").read_text(
            encoding="utf-8"
        )
    )
    conn.close()

    vs.init_vec_table()

    # Insert a metadata row
    conn = sqlite3.connect(str(_TMP_PATH))
    cur = conn.execute(
        "INSERT INTO vector_chunks (source, chunk_id, agent_name, domain, text) "
        "VALUES (?, ?, ?, ?, ?)",
        ("test.md", 0, "test-agent", "test", "hello world embedding test"),
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()

    # Insert a fake 768-dim embedding (all zeros except first element)
    fake_emb = [0.0] * 768
    fake_emb[0] = 1.0
    vs.upsert_vector(row_id, fake_emb)

    # KNN search should return the chunk
    results = vs.search_vectors(fake_emb, top_k=1)
    assert len(results) == 1
    assert results[0]["source"] == "test.md"
    assert results[0]["text"] == "hello world embedding test"
    assert results[0]["distance"] < 0.01  # near-zero distance to itself


# ── Cleanup ───────────────────────────────────────────────────────────────────


def teardown_module(_module):
    """Remove temp DB file."""
    try:
        Path(_TMP_PATH).unlink(missing_ok=True)
    except Exception:
        pass
