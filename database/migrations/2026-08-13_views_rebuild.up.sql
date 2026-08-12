-- Stage 4: views rebuild.
--
-- Repairs v_cost_savings (was keying off model_tier, an INTEGER column that is
-- 0 or 3 for ~all rows in practice — never 1/2 — so the tier CASE collapsed
-- to 'unknown'/'A (paid)' only; and its cost was a flat 666-token-per-call
-- Sonnet proxy applied even to $0 tiers) and v_tier_distribution (hardcoded
-- 5-agent allowlist that misses claude-sonnet-4-6 and invoice-extractor, the
-- top 2 agents by volume — 1688 and 664 rows respectively, both silently
-- landing in the 'B' catch-all). Both now derive from the real `tier` TEXT
-- column and, for cost, the real `estimated_cost_usd` column.
--
-- Adds 4 new views: v_action_project (D3/Correction B retroactive project
-- resolution — never mutates a row), v_action_category (D3 work_kind/intent
-- taxonomy), v_project_cost_weekly (the direct answer to "cost per project
-- per week, agent hours vs human hours"), v_agent_efficiency (request-level
-- success rate via request_id, cascade-retry rate).
--
-- DROP+CREATE required for the 2 repaired views (not IF NOT EXISTS) because
-- an existing production DB already has the old view body.

BEGIN TRANSACTION;

DROP VIEW IF EXISTS v_cost_savings;
CREATE VIEW v_cost_savings AS
SELECT
    date(timestamp) AS day,
    COALESCE(tier, 'unknown') AS tier,
    COUNT(*) AS actions,
    ROUND(AVG(duration_ms) / 1000.0, 1) AS avg_s,
    ROUND(SUM(COALESCE(estimated_cost_usd, 0)), 4) AS actual_cost_usd,
    -- Sonnet-equivalent reference proxy retained for comparison (unchanged formula).
    ROUND(COUNT(*) * 666 * 0.000015, 4) AS sonnet_equivalent_usd
FROM agent_actions
WHERE timestamp >= date('now', '-30 days')
  AND (error_message IS NULL OR error_message NOT LIKE 'reconciled:%')
GROUP BY day, tier;

DROP VIEW IF EXISTS v_tier_distribution;
CREATE VIEW v_tier_distribution AS
SELECT
    date(timestamp) AS day,
    COALESCE(tier, 'unknown') AS tier,
    COUNT(*) AS actions,
    ROUND(AVG(duration_ms)) AS avg_ms
FROM agent_actions
WHERE (error_message IS NULL OR error_message NOT LIKE 'reconciled:%')
GROUP BY day, tier;

DROP VIEW IF EXISTS v_action_project;
CREATE VIEW v_action_project AS
SELECT
    a.id,
    a.timestamp,
    a.session_id,
    a.agent_name,
    COALESCE(
        a.project,
        s.project,
        (SELECT pc.project FROM project_context pc
         WHERE pc.scope = 'global'
           AND pc.declared_at <= a.timestamp
           AND (pc.ended_at IS NULL OR pc.ended_at > a.timestamp)
         ORDER BY pc.declared_at DESC LIMIT 1),
        'unattributed'
    ) AS resolved_project
FROM agent_actions a
LEFT JOIN sessions s ON s.session_id = a.session_id;

DROP VIEW IF EXISTS v_action_category;
CREATE VIEW v_action_category AS
SELECT
    a.id,
    a.timestamp,
    a.session_id,
    a.agent_name,
    a.tool_used,
    a.action_type,
    CASE
        WHEN a.action_type = 'api_call' THEN 'llm_call'
        WHEN LOWER(COALESCE(a.file_path, '')) LIKE '%test_%.py%'
          OR LOWER(COALESCE(a.file_path, '')) LIKE '%/tests/%'
          OR LOWER(COALESCE(a.file_path, '')) LIKE '%pytest%'
            THEN 'test'
        WHEN a.tool_used IN ('Edit', 'Write', 'MultiEdit')
          AND (LOWER(COALESCE(a.file_path, '')) LIKE '%.md'
            OR LOWER(COALESCE(a.file_path, '')) LIKE '%.rst'
            OR LOWER(COALESCE(a.file_path, '')) LIKE '%.txt'
            OR LOWER(COALESCE(a.file_path, '')) LIKE '%/docs/%')
            THEN 'docs'
        WHEN a.tool_used IN ('Edit', 'Write', 'MultiEdit') THEN 'code'
        WHEN a.tool_used = 'Bash'
          AND (LOWER(COALESCE(a.file_path, '')) LIKE '%systemctl%'
            OR LOWER(COALESCE(a.file_path, '')) LIKE '%crontab%'
            OR LOWER(COALESCE(a.file_path, '')) LIKE '%docker%'
            OR LOWER(COALESCE(a.file_path, '')) LIKE '%nginx%'
            OR LOWER(COALESCE(a.file_path, '')) LIKE '%pip install%')
            THEN 'infra'
        WHEN a.tool_used IN ('Read', 'Grep', 'Glob', 'WebFetch', 'WebSearch')
          OR a.tool_used LIKE 'mcp\_\_%' ESCAPE '\'
            THEN 'research'
        ELSE 'other'
    END AS work_kind,
    -- intent: parsed from conventional-commit prefixes on `git commit -m` Bash
    -- rows only; NULL everywhere else (per-commit granularity, not per-action).
    CASE
        WHEN a.tool_used = 'Bash' AND LOWER(COALESCE(a.file_path, '')) LIKE '%git commit%' THEN
            CASE
                WHEN LOWER(a.file_path) LIKE '%fix:%' OR LOWER(a.file_path) LIKE '%fix(%' THEN 'fix'
                WHEN LOWER(a.file_path) LIKE '%feat:%' OR LOWER(a.file_path) LIKE '%feat(%' THEN 'feature'
                WHEN LOWER(a.file_path) LIKE '%refactor:%' OR LOWER(a.file_path) LIKE '%refactor(%' THEN 'refactor'
                WHEN LOWER(a.file_path) LIKE '%perf:%' OR LOWER(a.file_path) LIKE '%perf(%' THEN 'perf'
                WHEN LOWER(a.file_path) LIKE '%chore:%' OR LOWER(a.file_path) LIKE '%chore(%' THEN 'chore'
                WHEN LOWER(a.file_path) LIKE '%docs:%' OR LOWER(a.file_path) LIKE '%docs(%' THEN 'docs'
                ELSE NULL
            END
        ELSE NULL
    END AS intent
FROM agent_actions a;

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
    COALESCE(human_agg.human_hours, 0) AS human_hours,
    CASE WHEN COALESCE(human_agg.human_hours, 0) > 0
         THEN ROUND(agent_agg.cost_usd / human_agg.human_hours, 4)
         ELSE NULL END AS usd_per_human_hour
FROM agent_agg
LEFT JOIN human_agg
  ON human_agg.project = agent_agg.project AND human_agg.iso_week = agent_agg.iso_week
ORDER BY agent_agg.iso_week DESC, agent_agg.cost_usd DESC;

DROP VIEW IF EXISTS v_agent_efficiency;
CREATE VIEW v_agent_efficiency AS
WITH per_request AS (
    SELECT
        a.request_id,
        a.agent_name,
        vap.resolved_project AS project,
        COUNT(*) AS attempts,
        MAX(a.success) AS request_succeeded,
        SUM(COALESCE(a.duration_ms, 0)) AS request_duration_ms,
        SUM(COALESCE(a.estimated_cost_usd, 0)) AS request_cost_usd,
        SUM(COALESCE(a.tokens_input, 0) + COALESCE(a.tokens_output, 0)) AS request_tokens
    FROM agent_actions a
    JOIN v_action_project vap ON vap.id = a.id
    WHERE a.request_id IS NOT NULL
      AND (a.error_message IS NULL OR a.error_message NOT LIKE 'reconciled:%')
    GROUP BY a.request_id, a.agent_name, vap.resolved_project
)
SELECT
    agent_name,
    project,
    COUNT(*) AS total_requests,
    ROUND(AVG(request_succeeded) * 100, 1) AS success_rate_pct,
    ROUND(AVG(request_duration_ms)) AS avg_duration_ms,
    ROUND(
        SUM(CASE WHEN request_succeeded = 1 THEN request_cost_usd ELSE 0 END)
        / NULLIF(SUM(CASE WHEN request_succeeded = 1 THEN 1 ELSE 0 END), 0), 6
    ) AS avg_cost_usd_per_success,
    ROUND(
        SUM(CASE WHEN request_succeeded = 1 THEN request_tokens ELSE 0 END) * 1.0
        / NULLIF(SUM(CASE WHEN request_succeeded = 1 THEN 1 ELSE 0 END), 0), 1
    ) AS avg_tokens_per_success,
    ROUND(SUM(CASE WHEN attempts > 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS cascade_retry_rate_pct
FROM per_request
GROUP BY agent_name, project
ORDER BY total_requests DESC;

INSERT INTO schema_migrations (version, applied_at)
VALUES ('2026-08-13_views_rebuild', datetime('now'));

COMMIT;
