-- DQIII8 — Fix vector_chunks UNIQUE constraint (add domain column)
-- Problem: UNIQUE(source, chunk_id, agent_name) collides when multiple knowledge
--          domains share a filename (e.g., IDENTITY.md in all 5 global domains).
-- Fix: Add domain to UNIQUE key so each domain's files are independent.

CREATE TABLE IF NOT EXISTS vector_chunks_new (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT    NOT NULL,
    chunk_id    INTEGER NOT NULL,
    agent_name  TEXT,
    domain      TEXT,
    text        TEXT    NOT NULL,
    indexed_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (source, chunk_id, agent_name, domain)
);

INSERT OR IGNORE INTO vector_chunks_new
    (id, source, chunk_id, agent_name, domain, text, indexed_at)
SELECT id, source, chunk_id, agent_name, domain, text, indexed_at
FROM vector_chunks;

DROP TABLE vector_chunks;
ALTER TABLE vector_chunks_new RENAME TO vector_chunks;

CREATE INDEX IF NOT EXISTS idx_vc_agent  ON vector_chunks (agent_name);
CREATE INDEX IF NOT EXISTS idx_vc_domain ON vector_chunks (domain);
