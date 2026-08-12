-- Stage 2 (DB attribution rebuild) — project_context: single source of truth
-- for "current project", replacing the two dead file-glob resolvers
-- (session_start.py, user_prompt_submit.py) that both target the nonexistent
-- /root/dqiii8/projects/ dir (Correction C). Mirrors human_hours' shape:
-- append-only by convention, one closing UPDATE, partial-unique-index-enforced
-- single open row per scope.
-- Design: /root/.claude/plans/majestic-wondering-brook.md, D1/D2/Correction I.1.
-- Idempotent: all CREATE use IF NOT EXISTS. Doble anclaje: must match the
-- block added to database/schema_v2.sql (SSOT for fresh installs).

BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS project_context (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  scope       TEXT NOT NULL,          -- 'global' | a concrete session_id
  project     TEXT NOT NULL,          -- validated against my-projects/* + 'dqiii8-core'
  declared_at TEXT NOT NULL,
  declared_by TEXT NOT NULL CHECK(declared_by IN ('telegram','cli','session_start','prompt','api')),
  source_detail TEXT,
  ended_at    TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_project_context_open
  ON project_context(scope) WHERE ended_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_project_context_project
  ON project_context(project, declared_at);

-- Shadow layer (D2): fuzzy NL matcher candidates, observability only — never
-- read by resolve_project() or attribution. Measures real recall loss from
-- the strict write-layer matcher before ever loosening it.
CREATE TABLE IF NOT EXISTS nl_match_candidates (
  id                       INTEGER PRIMARY KEY AUTOINCREMENT,
  prompt_excerpt           TEXT NOT NULL,
  matched_project           TEXT NOT NULL,
  confidence                REAL NOT NULL,
  matched_at                TEXT NOT NULL,
  precision_matcher_agreed  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS schema_migrations (
  version     TEXT PRIMARY KEY,
  applied_at  TEXT NOT NULL
);

INSERT INTO schema_migrations (version, applied_at)
VALUES ('2026-08-13_project_context', strftime('%Y-%m-%dT%H:%M:%SZ','now'))
ON CONFLICT(version) DO NOTHING;

COMMIT;
