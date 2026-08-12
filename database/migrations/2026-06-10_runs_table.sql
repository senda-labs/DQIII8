-- STATUS: SUPERSEDED (2026-07-05 remediation) — never applied to any DB, zero code
-- references to a `runs` table were found (audit 2026-07-05 §3 HIGH). Kept as a
-- design record only. If a unified runs table is ever needed, re-review first.
-- 2026-06-10: unified runs table — one row per pipeline execution.
-- Documented schema addition (schema_v2.sql intentionally NOT touched;
-- migrations/ is the change journal — see docs/decisions/2026-06-10-metrics-db-rename.md).
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT,
    pipeline    TEXT NOT NULL,             -- 'dq', 'intl-reports', 'content-automation', 'benchmark', ...
    slug        TEXT,                      -- unit identifier when applicable
    model       TEXT,
    cost_usd    REAL DEFAULT 0,
    duration_ms INTEGER,
    result      TEXT CHECK(result IN ('success','degraded','failed','aborted')),
    qa_score    REAL,                      -- 0-100 when a QA gate ran
    notes       TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_pipeline_time ON runs(pipeline, started_at);
CREATE INDEX IF NOT EXISTS idx_runs_result ON runs(result);
