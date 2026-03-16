-- Migration: resource_claims table
-- Lightweight multi-agent resource locking.
-- TTL-based: claims expire automatically; no manual release required.

CREATE TABLE IF NOT EXISTS resource_claims (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    resource    TEXT NOT NULL UNIQUE,      -- file path or logical resource name
    agent       TEXT NOT NULL,             -- agent_name that holds the claim
    session_id  TEXT NOT NULL,
    claimed_at  TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at  TEXT NOT NULL              -- datetime('now', '+30 minutes') on insert
);

CREATE INDEX IF NOT EXISTS idx_resource_claims_expires
    ON resource_claims(expires_at);
