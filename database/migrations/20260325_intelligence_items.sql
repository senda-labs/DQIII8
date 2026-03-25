-- Migration: intelligence_items table
-- Date: 2026-03-25
-- Purpose: Store classified news/updates from AI sources for daily digest

CREATE TABLE IF NOT EXISTS intelligence_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    summary TEXT,
    relevance TEXT CHECK(relevance IN ('HIGH','MEDIUM','LOW','IGNORE')),
    action_type TEXT CHECK(action_type IN ('integrate','evaluate','monitor','ignore')),
    affects TEXT,
    processed INTEGER DEFAULT 0,
    chunk_generated INTEGER DEFAULT 0,
    notified INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_intel_relevance ON intelligence_items(relevance);
CREATE INDEX IF NOT EXISTS idx_intel_created ON intelligence_items(created_at);
