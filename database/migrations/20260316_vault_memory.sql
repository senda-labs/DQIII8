-- Migration: vault_memory table
-- Adds persistent factual knowledge triples extracted at session end.

CREATE TABLE IF NOT EXISTS vault_memory (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    subject     TEXT NOT NULL,
    predicate   TEXT NOT NULL,
    object      TEXT NOT NULL,
    project     TEXT DEFAULT '',
    confidence  REAL DEFAULT 1.0,
    times_seen  INTEGER DEFAULT 1,
    source      TEXT DEFAULT 'session_stop',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(subject, predicate, object)
);

CREATE INDEX IF NOT EXISTS idx_vault_memory_project
    ON vault_memory(project, last_seen);
