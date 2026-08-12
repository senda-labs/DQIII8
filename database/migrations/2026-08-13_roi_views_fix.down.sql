-- Reverts 2026-08-13_roi_views_fix.up.sql back to 2026-08-13_roi_views.up.sql's
-- v_project_roi/v_budget_deviation definitions.

DROP VIEW IF EXISTS v_project_roi;
CREATE VIEW v_project_roi AS
WITH value_agg AS (
    SELECT project,
           ROUND(SUM(CASE WHEN tipo IN ('fee_cobrado','hito_entregado') THEN importe_eur ELSE 0 END), 2) AS ingresos_eur
    FROM project_value GROUP BY project
),
cost_agg AS (
    SELECT project, ROUND(SUM(cost_usd), 4) AS cost_usd_technical, ROUND(SUM(human_hours), 2) AS human_hours
    FROM v_project_cost_weekly GROUP BY project
),
infra_agg AS (
    SELECT project, ROUND(SUM(infra_cost_eur), 2) AS infra_cost_eur
    FROM v_infra_cost_weekly GROUP BY project
),
rate AS (
    SELECT rate_eur_hour FROM labor_rates ORDER BY effective_date DESC, id DESC LIMIT 1
)
SELECT
    value_agg.project,
    value_agg.ingresos_eur,
    COALESCE(cost_agg.cost_usd_technical, 0) AS coste_tecnico_usd_informativo,
    COALESCE(cost_agg.human_hours, 0) AS human_hours,
    ROUND(COALESCE(cost_agg.human_hours, 0) * (SELECT rate_eur_hour FROM rate), 2) AS coste_humano_eur,
    COALESCE(infra_agg.infra_cost_eur, 0) AS coste_infra_eur,
    ROUND(value_agg.ingresos_eur
          - (COALESCE(cost_agg.human_hours, 0) * (SELECT rate_eur_hour FROM rate))
          - COALESCE(infra_agg.infra_cost_eur, 0), 2) AS roi_eur
FROM value_agg
LEFT JOIN cost_agg ON cost_agg.project = value_agg.project
LEFT JOIN infra_agg ON infra_agg.project = value_agg.project;

DROP VIEW IF EXISTS v_budget_deviation;
CREATE VIEW v_budget_deviation AS
WITH cost_agg AS (
    SELECT project, ROUND(SUM(human_hours), 2) AS human_hours
    FROM v_project_cost_weekly GROUP BY project
),
infra_agg AS (
    SELECT project, ROUND(SUM(infra_cost_eur), 2) AS infra_cost_eur
    FROM v_infra_cost_weekly GROUP BY project
),
rate AS (
    SELECT rate_eur_hour FROM labor_rates ORDER BY effective_date DESC, id DESC LIMIT 1
)
SELECT
    pb.project,
    pb.presupuesto_eur,
    COALESCE(cost_agg.human_hours, 0) AS human_hours,
    ROUND(COALESCE(cost_agg.human_hours, 0) * (SELECT rate_eur_hour FROM rate), 2) AS coste_humano_eur,
    COALESCE(infra_agg.infra_cost_eur, 0) AS coste_infra_eur,
    ROUND((COALESCE(cost_agg.human_hours, 0) * (SELECT rate_eur_hour FROM rate)) + COALESCE(infra_agg.infra_cost_eur, 0), 2) AS coste_total_eur,
    CASE WHEN pb.presupuesto_eur > 0
         THEN ROUND((((COALESCE(cost_agg.human_hours, 0) * (SELECT rate_eur_hour FROM rate)) + COALESCE(infra_agg.infra_cost_eur, 0)) / pb.presupuesto_eur - 1) * 100.0, 1)
         ELSE NULL END AS desviacion_pct
FROM project_budget pb
LEFT JOIN cost_agg ON cost_agg.project = pb.project
LEFT JOIN infra_agg ON infra_agg.project = pb.project;

DELETE FROM schema_migrations WHERE version = '2026-08-13_roi_views_fix';
