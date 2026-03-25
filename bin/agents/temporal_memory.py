#!/usr/bin/env python3
"""
DQIII8 — Temporal Memory
Entity-predicate-value fact store with temporal validity windows.

Schema lives in database/schema_temporal.sql.

Public API:
    add_episode(session_id, agent_name, summary, domain)  → episode_id
    add_fact(entity, predicate, value, domain, source_episode_id, confidence) → fact_id
    query_facts(entity, predicate, domain, as_of)          → list[dict]
    search_facts(query_text, top_k, domain, as_of)         → list[dict]  (text LIKE)
    add_relation(subject, predicate, object, domain, source_episode_id) → relation_id
    invalidate_fact(fact_id, reason_fact_id)
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DQIII8_ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
DB_PATH = DQIII8_ROOT / "database" / "dqiii8.db"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


# ── Episodes ──────────────────────────────────────────────────────────────────


def add_episode(
    session_id: str,
    agent_name: str = "",
    summary: str = "",
    domain: str = "",
    metadata: dict | None = None,
) -> int:
    """Create an episode record and return its id."""
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO episodes (session_id, agent_name, summary, domain, metadata) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, agent_name, summary, domain, json.dumps(metadata or {})),
        )
        return cur.lastrowid


# ── Facts ─────────────────────────────────────────────────────────────────────


def add_fact(
    entity: str,
    predicate: str,
    value: str,
    domain: str = "",
    source_episode_id: int | None = None,
    confidence: float = 1.0,
    metadata: dict | None = None,
) -> int:
    """
    Insert a new fact. Invalidates any currently-valid fact with the same
    (entity, predicate, domain) triple — implements temporal supersession.

    Returns the new fact_id.
    """
    now = _now_iso()
    with _conn() as conn:
        # Find currently valid facts for this (entity, predicate, domain)
        existing = conn.execute(
            "SELECT id FROM facts "
            "WHERE entity = ? AND predicate = ? AND domain = ? AND valid_until IS NULL",
            (entity, predicate, domain),
        ).fetchall()

        # Insert the new fact first so we have its id
        cur = conn.execute(
            "INSERT INTO facts "
            "(entity, predicate, value, domain, source_episode_id, "
            " valid_from, confidence, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entity,
                predicate,
                value,
                domain,
                source_episode_id,
                now,
                confidence,
                json.dumps(metadata or {}),
            ),
        )
        new_id = cur.lastrowid

        # Invalidate superseded facts
        for row in existing:
            conn.execute(
                "UPDATE facts SET valid_until = ?, invalidated_by = ? WHERE id = ?",
                (now, new_id, row["id"]),
            )

    return new_id


def invalidate_fact(fact_id: int, reason_fact_id: int | None = None) -> None:
    """Manually close the validity window of a fact."""
    with _conn() as conn:
        conn.execute(
            "UPDATE facts SET valid_until = ?, invalidated_by = ? WHERE id = ?",
            (_now_iso(), reason_fact_id, fact_id),
        )


def query_facts(
    entity: str | None = None,
    predicate: str | None = None,
    domain: str | None = None,
    as_of: str | None = None,
    include_expired: bool = False,
    session_id: str | None = None,
) -> list[dict]:
    """
    Return facts matching the given filters.

    as_of: ISO datetime string — return facts valid at that point in time.
           Defaults to "currently valid" (valid_until IS NULL).
    include_expired: if True, return all historical facts regardless of validity.
    """
    clauses: list[str] = []
    params: list = []

    if entity is not None:
        clauses.append("entity = ?")
        params.append(entity)
    if predicate is not None:
        clauses.append("predicate = ?")
        params.append(predicate)
    if domain is not None:
        clauses.append("domain = ?")
        params.append(domain)

    if not include_expired:
        if as_of:
            clauses.append(
                "valid_from <= ? AND (valid_until IS NULL OR valid_until > ?)"
            )
            params.extend([as_of, as_of])
        else:
            clauses.append("valid_until IS NULL")

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM facts {where} ORDER BY valid_from DESC"

    with _conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        results = [dict(r) for r in rows]

    # Log accesses if session_id provided
    if session_id and results:
        with _conn() as conn:
            conn.executemany(
                "INSERT INTO fact_access_log (fact_id, session_id, access_type) VALUES (?,?,?)",
                [(r["id"], session_id, "query") for r in results],
            )

    return results


# ── Fact text search ───────────────────────────────────────────────────────────


def search_facts(
    query_text: str,
    top_k: int = 10,
    domain: str | None = None,
    as_of: str | None = None,
    session_id: str | None = None,
) -> list[dict]:
    """
    Text-based fact search using LIKE on (entity + predicate + value).
    For vector-based search over knowledge chunks, use vector_store.search_vectors().

    Returns facts ranked by recency (valid_from DESC).
    """
    terms = [t.strip() for t in query_text.split() if t.strip()]
    if not terms:
        return []

    clauses: list[str] = []
    params: list = []

    # Temporal filter
    if as_of:
        clauses.append("valid_from <= ? AND (valid_until IS NULL OR valid_until > ?)")
        params.extend([as_of, as_of])
    else:
        clauses.append("valid_until IS NULL")

    if domain:
        clauses.append("domain = ?")
        params.append(domain)

    # Text match: any term in entity, predicate, or value
    term_clauses = []
    for term in terms:
        term_clauses.append("(entity LIKE ? OR predicate LIKE ? OR value LIKE ?)")
        params.extend([f"%{term}%", f"%{term}%", f"%{term}%"])
    if term_clauses:
        clauses.append("(" + " OR ".join(term_clauses) + ")")

    where = "WHERE " + " AND ".join(clauses)
    sql = f"SELECT * FROM facts {where} ORDER BY valid_from DESC LIMIT ?"
    params.append(top_k)

    with _conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        results = [dict(r) for r in rows]

    if session_id and results:
        with _conn() as conn:
            conn.executemany(
                "INSERT INTO fact_access_log (fact_id, session_id, query_text, access_type) "
                "VALUES (?,?,?,?)",
                [(r["id"], session_id, query_text, "search") for r in results],
            )

    return results


# ── Relations ─────────────────────────────────────────────────────────────────


def add_relation(
    subject: str,
    predicate: str,
    object_: str,
    domain: str = "",
    source_episode_id: int | None = None,
    confidence: float = 1.0,
    metadata: dict | None = None,
) -> int:
    """Insert a directed relation edge. Returns relation_id."""
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO relations "
            "(subject, predicate, object, domain, source_episode_id, confidence, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                subject,
                predicate,
                object_,
                domain,
                source_episode_id,
                confidence,
                json.dumps(metadata or {}),
            ),
        )
        return cur.lastrowid


def query_relations(
    subject: str | None = None,
    predicate: str | None = None,
    object_: str | None = None,
    domain: str | None = None,
    as_of: str | None = None,
) -> list[dict]:
    """Return currently-valid relations matching filters."""
    clauses: list[str] = []
    params: list = []

    if subject is not None:
        clauses.append("subject = ?")
        params.append(subject)
    if predicate is not None:
        clauses.append("predicate = ?")
        params.append(predicate)
    if object_ is not None:
        clauses.append("object = ?")
        params.append(object_)
    if domain is not None:
        clauses.append("domain = ?")
        params.append(domain)

    if as_of:
        clauses.append("valid_from <= ? AND (valid_until IS NULL OR valid_until > ?)")
        params.extend([as_of, as_of])
    else:
        clauses.append("valid_until IS NULL")

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM relations {where} ORDER BY valid_from DESC"

    with _conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


# ── CLI ───────────────────────────────────────────────────────────────────────


def _stats() -> None:
    with _conn() as conn:
        facts_total = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        facts_active = conn.execute(
            "SELECT COUNT(*) FROM facts WHERE valid_until IS NULL"
        ).fetchone()[0]
        relations = conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
        episodes = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
        accesses = conn.execute("SELECT COUNT(*) FROM fact_access_log").fetchone()[0]

    print("── Temporal Memory Stats ──────────────────")
    print(f"  Episodes   : {episodes}")
    print(f"  Facts      : {facts_active} active / {facts_total} total")
    print(f"  Relations  : {relations}")
    print(f"  Accesses   : {accesses}")
    print("────────────────────────────────────────────")


if __name__ == "__main__":
    import sys

    if "--stats" in sys.argv:
        _stats()
    elif "--demo" in sys.argv:
        ep = add_episode("demo-session", "python-specialist", "Demo run", "python")
        f1 = add_fact("python", "version", "3.10", "python", ep)
        f2 = add_fact("python", "version", "3.12", "python", ep)  # supersedes f1
        r1 = add_relation("python", "is_a", "programming_language", "python", ep)
        print(f"Episode={ep}, fact_v310={f1} (now expired), fact_v312={f2}, rel={r1}")
        facts = query_facts("python", "version", "python")
        print("Active facts:", [f["value"] for f in facts])
        _stats()
    else:
        _stats()
