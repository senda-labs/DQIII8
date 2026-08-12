-- Stage 8: ROI/budget/rework/fragmentation views. See
-- /root/.claude/plans/distributed-wobbling-gem.md for full rationale.
-- Depends on 2026-08-13_project_value_and_budget.up.sql and
-- 2026-08-13_project_context_status.up.sql having already been applied.

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

DROP VIEW IF EXISTS v_context_fragmentation;
CREATE VIEW v_context_fragmentation AS
WITH gaps AS (
    SELECT vap.resolved_project AS project, a.session_id,
           (julianday(a.timestamp) - julianday(
               LAG(a.timestamp) OVER (PARTITION BY a.session_id ORDER BY a.timestamp)
           )) * 86400.0 AS gap_seconds
    FROM agent_actions a
    JOIN v_action_project vap ON vap.id = a.id
)
SELECT project, COUNT(*) AS gap_samples, ROUND(AVG(gap_seconds), 1) AS mean_gap_s, ROUND(MAX(gap_seconds), 1) AS max_gap_s
FROM gaps WHERE gap_seconds IS NOT NULL GROUP BY project;

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

DROP VIEW IF EXISTS v_rework_signal;
CREATE VIEW v_rework_signal AS
SELECT
    a1.id AS first_action_id, a2.id AS rework_action_id,
    vap1.resolved_project AS project, a1.file_path,
    a1.timestamp AS first_edit_at, a2.timestamp AS reedit_at,
    ROUND((julianday(a2.timestamp) - julianday(a1.timestamp)) * 24.0, 2) AS hours_between
FROM agent_actions a1
JOIN v_action_project vap1 ON vap1.id = a1.id
JOIN agent_actions a2
  ON a2.file_path = a1.file_path AND a2.id != a1.id AND a2.timestamp > a1.timestamp
 AND (julianday(a2.timestamp) - julianday(a1.timestamp)) * 24.0 <= 24.0
WHERE a1.tool_used IN ('Edit','Write','MultiEdit') AND a2.tool_used IN ('Edit','Write','MultiEdit')
  AND a1.file_path IS NOT NULL;

INSERT INTO schema_migrations (version, applied_at)
VALUES ('2026-08-13_roi_views', datetime('now'));
