-- 2026-07-05: performance indexes (audit 2026-07-05 §3 MED — missing indexes).
-- Applied 2026-07-05; recorded in schema_migrations. Idempotent.
CREATE INDEX IF NOT EXISTS idx_error_log_action_id ON error_log(action_id);
CREATE INDEX IF NOT EXISTS idx_amplification_log_created_at ON amplification_log(created_at);
CREATE INDEX IF NOT EXISTS idx_token_usage_timestamp ON token_usage(timestamp);
