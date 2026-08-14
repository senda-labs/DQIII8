"""
Tests for bin/agents/vector_store.py and bin/agents/hybrid_search.py.

Split out of test_temporal_memory.py (review 2026-06-10) when temporal_memory /
memory_decay were archived: the facts/fact_access_log tables live readonly in
dqiii8_knowledge.db (moved from dqiii8_metrics.db, DB-consolidation 2026-08-14)
and the relevance lane no-ops in production. Vector + FTS5 + RRF coverage is
preserved here.

Run: python3 -m pytest tests/test_vector_hybrid_search.py -v
"""

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

# Skip entire module if sqlite_vec extension is not installed
def _sqlite_vec_available() -> bool:
    try:
        import sqlite3 as _s, sqlite_vec as _sv
        c = _s.connect(":memory:")
        c.enable_load_extension(True)
        _sv.load(c)
        return True
    except Exception:
        return False

pytestmark = pytest.mark.skipif(
    not _sqlite_vec_available(),
    reason="sqlite_vec extension not installed — run: pip install sqlite-vec",
)

# Point to test DB so we don't pollute dqiii8.db
_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB.close()
_TMP_PATH = Path(_TMP_DB.name)

sys.path.insert(0, str(Path(__file__).parent.parent / "bin" / "agents"))

import hybrid_search as hs  # noqa: E402
import vector_store as vs  # noqa: E402

vs.DB_PATH = _TMP_PATH
hs.DB_PATH = _TMP_PATH

# Apply legacy temporal schema (still defines vector_chunks used by these tests)
_SCHEMA = Path(__file__).parent.parent / "database" / "legacy" / "schema_temporal.sql"


@pytest.fixture(autouse=True)
def _fresh_db():
    """Re-create schema in temp DB before each test."""
    conn = sqlite3.connect(str(_TMP_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
    conn.close()
    yield
    conn = sqlite3.connect(str(_TMP_PATH))
    for table in ("fact_access_log", "facts", "relations", "episodes", "vector_chunks"):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.commit()
    conn.close()


def _apply_fts5(conn: sqlite3.Connection) -> None:
    """Create FTS5 tables in temp DB (not in schema_temporal.sql — loaded at runtime)."""
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            source, text, domain, agent_name,
            content='vector_chunks', content_rowid='id'
        )
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
            entity, predicate, value, domain,
            content='facts', content_rowid='id'
        )
    """)
    conn.commit()


def test_vector_store_init_and_upsert():
    """vec0 table can be created and vectors inserted/searched."""
    vs.DB_PATH = _TMP_PATH  # re-assert in case another module clobbered it
    vs.init_vec_table()

    conn = sqlite3.connect(str(_TMP_PATH))
    cur = conn.execute(
        "INSERT INTO vector_chunks (source, chunk_id, agent_name, domain, text) "
        "VALUES (?, ?, ?, ?, ?)",
        ("test.md", 0, "test-agent", "test", "hello world embedding test"),
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()

    fake_emb = [0.0] * 1024
    fake_emb[0] = 1.0
    vs.upsert_vector(row_id, fake_emb)

    results = vs.search_vectors(fake_emb, top_k=1)
    assert len(results) == 1
    assert results[0]["source"] == "test.md"
    assert results[0]["text"] == "hello world embedding test"
    assert results[0]["distance"] < 0.01  # near-zero distance to itself


def test_hybrid_search_vector_only():
    """hybrid_search works when facts and relations tables are empty."""
    conn = sqlite3.connect(str(_TMP_PATH))
    _apply_fts5(conn)
    cur = conn.execute(
        "INSERT INTO vector_chunks (source, chunk_id, agent_name, domain, text) "
        "VALUES (?, ?, ?, ?, ?)",
        ("test_hybrid.md", 0, "", "test", "Kelly criterion optimal bet sizing"),
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()

    vs.init_vec_table()
    fake_emb = [0.0] * 1024
    fake_emb[0] = 1.0
    vs.upsert_vector(row_id, fake_emb)

    conn = sqlite3.connect(str(_TMP_PATH))
    conn.execute(
        "INSERT INTO chunks_fts(rowid, source, text, domain, agent_name) VALUES (?,?,?,?,?)",
        (row_id, "test_hybrid.md", "Kelly criterion optimal bet sizing", "test", ""),
    )
    conn.commit()
    conn.close()

    results, method = hs.hybrid_search("Kelly criterion", top_k=3, domain="test")
    assert len(results) >= 1
    assert method in ("vector_only", "hybrid", "keyword_only")
    assert all("text" in r for r in results)
    assert all("source" in r for r in results)
    assert all("search_method" in r for r in results)


def test_hybrid_search_keyword():
    """search_by_keywords finds FTS5 matches; returns search_method='keyword'."""
    hs.DB_PATH = _TMP_PATH  # re-assert in case another module clobbered it
    conn = sqlite3.connect(str(_TMP_PATH))
    _apply_fts5(conn)
    cur = conn.execute(
        "INSERT INTO vector_chunks (source, chunk_id, agent_name, domain, text) "
        "VALUES (?, ?, ?, ?, ?)",
        ("kelly.md", 0, "", "finance", "Kelly criterion is an optimal betting formula"),
    )
    row_id = cur.lastrowid
    conn.execute(
        "INSERT INTO chunks_fts(rowid, source, text, domain, agent_name) VALUES (?,?,?,?,?)",
        (row_id, "kelly.md", "Kelly criterion is an optimal betting formula", "finance", ""),
    )
    conn.commit()
    conn.close()

    results = hs.search_by_keywords("betting formula", top_k=5, domain="finance")
    assert len(results) >= 1
    assert all(r["search_method"] == "keyword" for r in results)
    assert any(
        "kelly" in r["source"].lower() or "kelly" in r["text"].lower() for r in results
    )


def test_rrf_merge():
    """reciprocal_rank_fusion merges two lists correctly."""
    list_a = [
        {"text": "alpha", "source": "a", "domain": "d", "score": 0.9, "search_method": "vector"},
        {"text": "beta", "source": "b", "domain": "d", "score": 0.7, "search_method": "vector"},
    ]
    list_b = [
        {"text": "beta", "source": "b", "domain": "d", "score": 0.8, "search_method": "keyword"},
        {"text": "gamma", "source": "c", "domain": "d", "score": 0.6, "search_method": "keyword"},
    ]

    merged = hs.reciprocal_rank_fusion([(list_a, 1.0), (list_b, 0.7)], k=60)

    texts = [r["text"] for r in merged]
    assert "alpha" in texts and "beta" in texts and "gamma" in texts

    beta_score = next(r["rrf_score"] for r in merged if r["text"] == "beta")
    gamma_score = next(r["rrf_score"] for r in merged if r["text"] == "gamma")
    assert beta_score > gamma_score, "beta (in both lists) should rank above gamma"

    assert texts.count("beta") == 1  # dedup
    beta_entry = next(r for r in merged if r["text"] == "beta")
    assert "vector" in beta_entry["search_method"]
    assert "keyword" in beta_entry["search_method"]


def test_apply_relevance_degrades_without_temporal_memory():
    """Post-archive contract: with temporal_memory removed from bin/agents/,
    _apply_relevance must return results unchanged instead of raising."""
    results = [{"id": 1, "text": "x", "rrf_score": 0.5, "item_type": "chunk"}]
    out = hs._apply_relevance(list(results), "probe query")
    assert len(out) == 1
    assert out[0]["text"] == "x"


def teardown_module(_module):
    try:
        _TMP_PATH.unlink(missing_ok=True)
    except Exception:
        pass
