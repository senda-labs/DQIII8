-- Rollback of 2026-08-13_project_context.up.sql

BEGIN TRANSACTION;

DROP INDEX IF EXISTS idx_project_context_project;
DROP INDEX IF EXISTS idx_project_context_open;

DROP TABLE IF EXISTS nl_match_candidates;
DROP TABLE IF EXISTS project_context;

DELETE FROM schema_migrations WHERE version = '2026-08-13_project_context';

COMMIT;
