-- Migration: model_satisfaction table
-- Date: 2026-03-18
-- Purpose: Track per-task user satisfaction to feed dynamic model routing

CREATE TABLE IF NOT EXISTS model_satisfaction (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp           TEXT    NOT NULL DEFAULT (datetime('now')),
    session_id          TEXT    NOT NULL,
    model_used          TEXT    NOT NULL,
    task_type           TEXT,                -- código|análisis|escritura|research|pipeline
    task_description    TEXT,                -- truncated to 100 chars
    duration_ms         INTEGER,
    technical_success   INTEGER DEFAULT 1,   -- 1=OK 0=ERROR
    user_satisfaction   INTEGER,             -- 0=no 1=yes NULL=no response
    tier_used           TEXT                 -- tier1|tier2|tier3
);

CREATE INDEX IF NOT EXISTS idx_satisfaction_model_type
    ON model_satisfaction(model_used, task_type, user_satisfaction);
