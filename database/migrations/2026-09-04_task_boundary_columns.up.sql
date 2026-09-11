-- Fase B: exact task-boundary grouping (see /root/.claude/plans/parsed-swinging-donut.md).
-- Additive, nullable columns — safe to apply to the live DB, idempotent to re-run.
-- schema_v2.sql itself is a blocked path for agent writes (PermissionAnalyzer DENY,
-- no carve-out); this migration file is the SSOT for these columns until a human
-- applies the matching edit to schema_v2.sql by hand.

-- agent_registry.end_time: NULL while the subagent is still running, set by
-- stop.py on SubagentStop.
ALTER TABLE agent_registry ADD COLUMN end_time TEXT;

-- agent_actions.agent_id: NULL means "top-level session action, no subagent
-- resolved" (a correct value, not a gap). Non-NULL is an exact FK into
-- agent_registry.agent_id, set by pre_tool_use.py at INSERT time.
ALTER TABLE agent_actions ADD COLUMN agent_id TEXT;

CREATE INDEX IF NOT EXISTS idx_agent_actions_agent_id ON agent_actions(agent_id);
