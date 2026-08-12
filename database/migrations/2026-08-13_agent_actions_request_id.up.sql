-- Stage 3: shared request_id across a cascade's fallback attempts.
-- Additive column + index; amends trg_agent_actions_close_once to protect
-- request_id the same way as every other INSERT-only column (Open Decision 2,
-- approved 2026-08-12). DROP+CREATE is required (not IF NOT EXISTS) because
-- the trigger body itself changes on an existing production DB.

-- Idempotency note: unlike schema_v2.sql's CREATE TABLE IF NOT EXISTS pattern,
-- SQLite has no ALTER TABLE ... ADD COLUMN IF NOT EXISTS. This file is a one-shot
-- migration applied manually to the existing production DB (per
-- .claude/rules/01_database_mutations.md: "apply manually: sqlite3 dqiii8.db <
-- schema_v2.sql"), tracked via the schema_migrations INSERT below — re-running it
-- against a DB that already has this migration applied will fail at this ALTER
-- (or, if run again after a manual rollback, at the schema_migrations PRIMARY KEY).
-- No repo precedent exists for a different guard (grep confirms this is the only
-- ALTER TABLE across all migrations/*.sql); a fresh install never runs this file at
-- all — it gets the column directly from schema_v2.sql.

BEGIN TRANSACTION;

ALTER TABLE agent_actions ADD COLUMN request_id TEXT;
CREATE INDEX IF NOT EXISTS idx_agent_actions_request_id ON agent_actions(request_id);

DROP TRIGGER IF EXISTS trg_agent_actions_close_once;
CREATE TRIGGER trg_agent_actions_close_once
BEFORE UPDATE ON agent_actions
FOR EACH ROW
WHEN OLD.end_time_ms IS NOT NULL
  OR NEW.id IS NOT OLD.id
  OR NEW.timestamp IS NOT OLD.timestamp
  OR NEW.session_id IS NOT OLD.session_id
  OR NEW.agent_name IS NOT OLD.agent_name
  OR NEW.project IS NOT OLD.project
  OR NEW.tool_used IS NOT OLD.tool_used
  OR NEW.file_path IS NOT OLD.file_path
  OR NEW.action_type IS NOT OLD.action_type
  OR NEW.start_time_ms IS NOT OLD.start_time_ms
  OR NEW.model_used IS NOT OLD.model_used
  OR NEW.tokens_used IS NOT OLD.tokens_used
  OR NEW.files_modified IS NOT OLD.files_modified
  OR NEW.worktree IS NOT OLD.worktree
  OR NEW.skills_active IS NOT OLD.skills_active
  OR NEW.blocked_by_hook IS NOT OLD.blocked_by_hook
  OR NEW.cost_eur IS NOT OLD.cost_eur
  OR NEW.model_tier IS NOT OLD.model_tier
  OR NEW.tokens_input IS NOT OLD.tokens_input
  OR NEW.tokens_output IS NOT OLD.tokens_output
  OR NEW.estimated_cost_usd IS NOT OLD.estimated_cost_usd
  OR NEW.tier IS NOT OLD.tier
  OR NEW.domain_enriched IS NOT OLD.domain_enriched
  OR NEW.domain IS NOT OLD.domain
  OR NEW.knowledge_chunks_used IS NOT OLD.knowledge_chunks_used
  OR NEW.energy_wh IS NOT OLD.energy_wh
  OR NEW.cpu_percent IS NOT OLD.cpu_percent
  OR NEW.input_tokens IS NOT OLD.input_tokens
  OR NEW.output_tokens IS NOT OLD.output_tokens
  OR NEW.notes IS NOT OLD.notes
  OR NEW.request_id IS NOT OLD.request_id
BEGIN
  SELECT RAISE(ABORT, 'agent_actions rows are immutable except a single close-out update (end_time_ms/duration_ms/success/error_message/bytes_written) while end_time_ms IS NULL');
END;

INSERT INTO schema_migrations (version, applied_at)
VALUES ('2026-08-13_agent_actions_request_id', datetime('now'));

COMMIT;
