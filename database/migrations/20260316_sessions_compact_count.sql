-- Migration: add compact_count to sessions
-- Tracks how many PreCompact events occurred in each session.

ALTER TABLE sessions ADD COLUMN compact_count INTEGER DEFAULT 0;
