-- Migration: security_findings table
-- Date: 2026-03-25
-- Purpose: Track red-team/blue-team security audit findings and their fix status

CREATE TABLE IF NOT EXISTS security_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    finding_id TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT,
    severity TEXT CHECK(severity IN ('CRITICAL','HIGH','MEDIUM','LOW')),
    file_path TEXT,
    line_number INTEGER,
    proof TEXT,
    is_vibe_pattern INTEGER DEFAULT 0,
    is_kill_chain INTEGER DEFAULT 0,
    status TEXT DEFAULT 'open' CHECK(status IN ('open','fixed','wontfix','false_positive')),
    fixed_at DATETIME,
    cycle_iteration INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_security_severity ON security_findings(severity);
CREATE INDEX IF NOT EXISTS idx_security_project ON security_findings(project);
