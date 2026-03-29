-- DQIII8 — Temporal Memory Schema (Bloque 9)
-- Apply: sqlite3 database/dqiii8.db < database/schema_temporal.sql

-- ── Episodes ─────────────────────────────────────────────────────────────────
-- A session or interaction that sourced a set of facts/relations
CREATE TABLE IF NOT EXISTS episodes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL,
    agent_name  TEXT,
    summary     TEXT,
    domain      TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    metadata    TEXT    -- JSON blob
);

-- ── Facts ─────────────────────────────────────────────────────────────────────
-- Temporal fact store: entity-predicate-value triples with validity windows
CREATE TABLE IF NOT EXISTS facts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    entity           TEXT    NOT NULL,
    predicate        TEXT    NOT NULL,
    value            TEXT    NOT NULL,
    domain           TEXT,
    source_episode_id INTEGER REFERENCES episodes(id),
    valid_from       TEXT    NOT NULL DEFAULT (datetime('now')),
    valid_until      TEXT,                          -- NULL = currently valid
    invalidated_by   INTEGER REFERENCES facts(id),  -- FK to superseding fact
    confidence       REAL    DEFAULT 1.0,
    metadata         TEXT    -- JSON blob
);

CREATE INDEX IF NOT EXISTS idx_facts_entity     ON facts (entity);
CREATE INDEX IF NOT EXISTS idx_facts_predicate  ON facts (predicate);
CREATE INDEX IF NOT EXISTS idx_facts_domain     ON facts (domain);
CREATE INDEX IF NOT EXISTS idx_facts_valid      ON facts (valid_until);
CREATE INDEX IF NOT EXISTS idx_facts_entity_pred ON facts (entity, predicate);

-- ── Relations ─────────────────────────────────────────────────────────────────
-- Directed entity-to-entity relations (knowledge graph edges)
CREATE TABLE IF NOT EXISTS relations (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    subject          TEXT    NOT NULL,
    predicate        TEXT    NOT NULL,
    object           TEXT    NOT NULL,
    domain           TEXT,
    source_episode_id INTEGER REFERENCES episodes(id),
    valid_from       TEXT    NOT NULL DEFAULT (datetime('now')),
    valid_until      TEXT,
    confidence       REAL    DEFAULT 1.0,
    metadata         TEXT    -- JSON blob
);

CREATE INDEX IF NOT EXISTS idx_relations_subject   ON relations (subject);
CREATE INDEX IF NOT EXISTS idx_relations_object    ON relations (object);
CREATE INDEX IF NOT EXISTS idx_relations_predicate ON relations (predicate);
CREATE INDEX IF NOT EXISTS idx_relations_domain    ON relations (domain);

-- ── Fact Access Log ───────────────────────────────────────────────────────────
-- Tracks which facts were retrieved and by whom (for LRU eviction, analytics)
CREATE TABLE IF NOT EXISTS fact_access_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_id     INTEGER NOT NULL REFERENCES facts(id),
    accessed_at TEXT    NOT NULL DEFAULT (datetime('now')),
    session_id  TEXT,
    query_text  TEXT,
    access_type TEXT    -- 'query' | 'search' | 'inject'
);

CREATE INDEX IF NOT EXISTS idx_fal_fact_id    ON fact_access_log (fact_id);
CREATE INDEX IF NOT EXISTS idx_fal_session    ON fact_access_log (session_id);
CREATE INDEX IF NOT EXISTS idx_fal_accessed   ON fact_access_log (accessed_at);

-- ── Vector Chunks (sqlite-vec) ────────────────────────────────────────────────
-- Flat metadata table; the vec0 virtual table lives in vector_store.py at init time
-- because sqlite-vec extension must be loaded before CREATE VIRTUAL TABLE.
CREATE TABLE IF NOT EXISTS vector_chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT    NOT NULL,   -- filename
    chunk_id    INTEGER NOT NULL,   -- index within file
    agent_name  TEXT,               -- which agent owns this chunk (NULL = global)
    domain      TEXT,               -- knowledge domain
    text        TEXT    NOT NULL,
    indexed_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (source, chunk_id, agent_name)
);

CREATE INDEX IF NOT EXISTS idx_vc_agent  ON vector_chunks (agent_name);
CREATE INDEX IF NOT EXISTS idx_vc_domain ON vector_chunks (domain);

-- ── FTS5 Full-Text Search (Bloque 9 Fase 2) ──────────────────────────────────
-- chunks_fts: keyword search over knowledge chunks (populated by vector_store.migrate_from_json)
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    source, text, domain, agent_name,
    content='vector_chunks',
    content_rowid='id'
);

-- facts_fts: keyword search over temporal facts (populated as facts accumulate in Fase 4)
CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
    entity, predicate, value, domain,
    content='facts',
    content_rowid='id'
);
