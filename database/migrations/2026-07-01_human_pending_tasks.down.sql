-- Rollback idempotente de 2026-07-01_human_pending_tasks.up.sql
-- Orden inverso: triggers -> índices -> tablas (FK-dependiente primero: human_pending_tasks antes de resumable_actions)

BEGIN TRANSACTION;

DROP TRIGGER IF EXISTS trg_hpt_immutable_exec_fields;
DROP TRIGGER IF EXISTS trg_hpt_valid_transition;

DROP INDEX IF EXISTS ix_expiry;
DROP INDEX IF EXISTS ix_poll;
DROP INDEX IF EXISTS ux_pending_dedup;

DROP TABLE IF EXISTS human_pending_tasks;
DROP TABLE IF EXISTS resumable_actions;

DELETE FROM schema_migrations WHERE version = '2026-07-01_human_pending_tasks';

COMMIT;
