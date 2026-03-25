-- Migration: cc_rate_limit table
-- Date: 2026-03-25
-- Purpose: Persistent rate limiting for /cc Telegram command (survives bot restarts)

CREATE TABLE IF NOT EXISTS cc_rate_limit (
    chat_id TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
