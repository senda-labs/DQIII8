-- Post-Stage-7 Opus adversarial review, P3 minor (deferred at the time,
-- addressed now): v_project_cost_weekly joined agent_agg (keyed on
-- v_action_project.resolved_project, a 4-step fallback chain — see
-- schema_v2.sql) against transcript_agg (keyed on raw sessions.project,
-- no fallback). A session with sessions.project IS NULL but attributable
-- via the open project_context global row (step 3 of the fallback) would
-- resolve to different project strings on each side of the LEFT JOIN,
-- silently dropping real transcript cost to 0 for that project/week
-- instead of joining it.
--
-- Fix: transcript_agg now applies the same project_context global-row
-- fallback sessions.project itself lacks (agent_actions.project doesn't
-- apply here — token_usage rows aren't agent_actions rows).

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
        COALESCE(
            s.project,
            (SELECT pc.project FROM project_context pc
             WHERE pc.scope = 'global'
               AND pc.declared_at <= tu.timestamp
               AND (pc.ended_at IS NULL OR pc.ended_at > tu.timestamp)
             ORDER BY pc.declared_at DESC LIMIT 1),
            'unattributed'
        ) AS project,
        strftime('%Y-%W', tu.timestamp) AS iso_week,
        ROUND(SUM(tu.cost_estimate), 4) AS cost_usd_listprice_equivalent
    FROM token_usage tu
    JOIN sessions s ON s.session_id = tu.session_id
    WHERE tu.source = 'claude_code_transcript'
    GROUP BY project, iso_week
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
VALUES ('2026-08-13_fix_project_cost_weekly_namespace', datetime('now'));
