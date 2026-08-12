-- Post-Stage-7 Opus adversarial review (P1-1/P1-2/P3-8) — approved, no
-- schema change, view repair only.
--
-- P1-1/P1-2: v_project_cost_weekly's cost_usd only ever read
-- agent_actions.estimated_cost_usd (real spend, ~$0 lifetime — free NIM
-- tiers), never Stage 5's transcript-derived list-price-equivalent figures
-- in token_usage (source='claude_code_transcript'), so the headline
-- "cost per project" view was disconnected from the only cost data that
-- actually moves. Adds cost_usd_listprice_equivalent as its own column
-- (never summed into cost_usd), joined via sessions.project — the bridge
-- schema_v2.sql's own token_usage comment already pointed to, and already
-- fully populated (37/37 sessions).
--
-- Known residual gap: agent_agg (agent_actions-driven) remains the outer
-- driving table, so a project/week with token_usage transcript cost but
-- zero agent_actions rows in that window would not surface. Judged
-- acceptable: every session producing transcript cost also produces
-- agent_actions rows via the same session's hooks.
--
-- P3-8: Opus flagged iso_week's strftime('%Y-%W') as not true ISO-8601 week
-- numbering (would need %G-%V). NOT fixed here: this VPS runs SQLite 3.45.1,
-- and %G/%V were only added in 3.46.0 — they silently return '' on this
-- build (confirmed live), which is worse than the mis-bucketing it was meant
-- to fix. Left as %Y-%W with this note; revisit if/when SQLite is upgraded.

DROP VIEW IF EXISTS v_project_cost_weekly;
CREATE VIEW v_project_cost_weekly AS
WITH agent_agg AS (
    SELECT
        vap.resolved_project AS project,
        strftime('%Y-%W', a.timestamp) AS iso_week,
        COUNT(*) AS actions,
        COUNT(DISTINCT a.agent_name) AS distinct_agents,
        COUNT(DISTINCT a.session_id) AS distinct_sessions,
        ROUND(SUM(COALESCE(a.duration_ms, 0)) / 3600000.0, 2) AS agent_hours,
        ROUND(SUM(COALESCE(a.estimated_cost_usd, 0)), 4) AS cost_usd
    FROM agent_actions a
    JOIN v_action_project vap ON vap.id = a.id
    WHERE (a.error_message IS NULL OR a.error_message NOT LIKE 'reconciled:%')
    GROUP BY vap.resolved_project, iso_week
),
transcript_agg AS (
    -- Correction E: Claude Code session cost is flat-rate OAuth (Claude Max),
    -- not per-token billing — this is a LIST-PRICE-EQUIVALENT relative-cost
    -- proxy, not real spend, and is kept in its own column rather than
    -- summed into cost_usd (real spend).
    SELECT
        s.project,
        strftime('%Y-%W', tu.timestamp) AS iso_week,
        ROUND(SUM(tu.cost_estimate), 4) AS cost_usd_listprice_equivalent
    FROM token_usage tu
    JOIN sessions s ON s.session_id = tu.session_id
    WHERE tu.source = 'claude_code_transcript' AND s.project IS NOT NULL
    GROUP BY s.project, iso_week
),
human_agg AS (
    SELECT
        project,
        strftime('%Y-%W', started_at) AS iso_week,
        ROUND(SUM((julianday(COALESCE(ended_at, datetime('now'))) - julianday(started_at)) * 24.0), 2) AS human_hours
    FROM human_hours
    GROUP BY project, iso_week
)
SELECT
    agent_agg.project,
    agent_agg.iso_week,
    agent_agg.actions,
    agent_agg.distinct_agents,
    agent_agg.distinct_sessions,
    agent_agg.agent_hours,
    agent_agg.cost_usd,
    COALESCE(transcript_agg.cost_usd_listprice_equivalent, 0) AS cost_usd_listprice_equivalent,
    COALESCE(human_agg.human_hours, 0) AS human_hours,
    CASE WHEN COALESCE(human_agg.human_hours, 0) > 0
         THEN ROUND(agent_agg.cost_usd / human_agg.human_hours, 4)
         ELSE NULL END AS usd_per_human_hour
FROM agent_agg
LEFT JOIN transcript_agg
  ON transcript_agg.project = agent_agg.project AND transcript_agg.iso_week = agent_agg.iso_week
LEFT JOIN human_agg
  ON human_agg.project = agent_agg.project AND human_agg.iso_week = agent_agg.iso_week
ORDER BY agent_agg.iso_week DESC, agent_agg.cost_usd DESC;

INSERT INTO schema_migrations (version, applied_at)
VALUES ('2026-08-13_fix_project_cost_weekly', datetime('now'));
