DROP VIEW IF EXISTS v_infra_cost_weekly;
CREATE VIEW v_infra_cost_weekly AS
WITH weekly_pool AS (
    SELECT ROUND(SUM(importe_eur_mes) / 4.345, 4) AS pool_eur
    FROM infra_costs
    WHERE activo_hasta IS NULL
),
project_hours AS (
    SELECT project, iso_week, agent_hours,
           SUM(agent_hours) OVER (PARTITION BY iso_week) AS total_hours_week
    FROM v_project_cost_weekly
)
SELECT
    ph.project,
    ph.iso_week,
    ROUND(CASE WHEN ph.total_hours_week > 0
               THEN (ph.agent_hours / ph.total_hours_week) * wp.pool_eur
               ELSE 0 END, 4) AS infra_cost_eur
FROM project_hours ph
CROSS JOIN weekly_pool wp;

DELETE FROM schema_migrations WHERE version = '2026-08-13_infra_cost_weekly_null_fix';
