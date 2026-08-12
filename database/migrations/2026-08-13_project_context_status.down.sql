ALTER TABLE project_context DROP COLUMN status;

DELETE FROM schema_migrations WHERE version = '2026-08-13_project_context_status';
