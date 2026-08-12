-- Rollback for 2026-08-13_views_rebuild.up.sql.
-- Drops the 4 new views and restores the 2 repaired views to their
-- pre-migration bodies (model_tier-keyed CASE, hardcoded agent allowlist).

BEGIN TRANSACTION;

DROP VIEW IF EXISTS v_agent_efficiency;
DROP VIEW IF EXISTS v_project_cost_weekly;
DROP VIEW IF EXISTS v_action_category;
DROP VIEW IF EXISTS v_action_project;

DROP VIEW IF EXISTS v_cost_savings;
CREATE VIEW v_cost_savings AS
SELECT
    date(timestamp) as day,
    CASE model_tier
        WHEN 1 THEN 'C (local $0)'
        WHEN 2 THEN 'B (cloud free)'
        WHEN 3 THEN 'A (paid)'
        ELSE 'unknown'
    END as tier,
    COUNT(*) as actions,
    ROUND(AVG(duration_ms)/1000.0, 1) as avg_s,
    ROUND(SUM(CASE WHEN model_tier = 3 THEN (666 * 0.000015) ELSE 0 END), 4) as actual_cost_usd,
    ROUND(COUNT(*) * 666 * 0.000015, 4) as sonnet_equivalent_usd
FROM agent_actions
WHERE timestamp >= date('now', '-30 days')
GROUP BY day, tier;

DROP VIEW IF EXISTS v_tier_distribution;
CREATE VIEW v_tier_distribution AS
SELECT
    date(timestamp) as day,
    CASE
        WHEN agent_name IN ('python-specialist','git-specialist','web-specialist',
            'algo-specialist','content-automator') THEN 'C'
        WHEN agent_name IN ('finance-specialist','auditor','orchestrator') THEN 'A'
        ELSE 'B'
    END as tier,
    COUNT(*) as actions,
    ROUND(AVG(duration_ms)) as avg_ms
FROM agent_actions
GROUP BY day, tier;

DELETE FROM schema_migrations WHERE version = '2026-08-13_views_rebuild';

COMMIT;
