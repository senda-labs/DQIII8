-- Disaster-scenario fix: v_infra_cost_weekly's weekly_pool CTE does
-- SUM(importe_eur_mes) over rows WHERE activo_hasta IS NULL. If every
-- infra_costs row is ever retired (or none seeded), SUM() over zero rows is
-- NULL, and that NULL propagates through the multiplication to
-- infra_cost_eur (NULL, not 0) — silently corrupting SUM(infra_cost_eur) in
-- v_project_roi/v_budget_deviation. Found via direct adversarial testing
-- against a scratch DB, 2026-08-12. Not currently triggered by live data
-- (3 active infra_costs rows), but a real gap: retiring all 3 items would
-- have hit it. Fix: COALESCE the pool to 0.

DROP VIEW IF EXISTS v_infra_cost_weekly;
CREATE VIEW v_infra_cost_weekly AS
WITH weekly_pool AS (
    SELECT ROUND(COALESCE(SUM(importe_eur_mes), 0) / 4.345, 4) AS pool_eur
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

-- v_project_roi and v_budget_deviation both SELECT * from v_infra_cost_weekly
-- and are pure views over it — no redefinition needed, they inherit the fix
-- automatically once v_infra_cost_weekly is recreated above.

INSERT INTO schema_migrations (version, applied_at)
VALUES ('2026-08-13_infra_cost_weekly_null_fix', datetime('now'));
