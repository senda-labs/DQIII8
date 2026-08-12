-- Rollback idempotente de 2026-07-02_human_pending_events.up.sql
-- Orden inverso: índice -> tabla.

BEGIN TRANSACTION;

DROP INDEX IF EXISTS ix_hpt_events_task;
DROP TABLE IF EXISTS human_pending_events;

DELETE FROM schema_migrations WHERE version = '2026-07-02_human_pending_events';

COMMIT;
