-- Stage 8 follow-up: fixes to v_project_roi/v_budget_deviation surfaced by the
-- /panel-review Opus pass (2026-08-12, report
-- database/audit_reports/panel-review-2026-08-12-210415-distributed-wobbling-gem.md).
-- Depends on 2026-08-13_roi_views.up.sql having already been applied.
--
-- P1: v_project_cost_weekly is FROM agent_agg LEFT JOIN human_agg, so a
-- (project, iso_week) with logged human_hours but zero agent_actions that
-- week is dropped entirely — coste_humano_eur was silently understated.
-- Fix: both views now sum human_hours directly from the human_hours table,
-- independent of agent_actions presence.
--
-- P2: v_project_roi was FROM value_agg (project_value) only, so a project
-- with real human/infra costs but no logged project_value row never
-- appeared — unbilled/loss-making work was invisible to ROI reporting.
-- Fix: FROM is now a union of every project appearing in value_agg,
-- human_agg or infra_agg, so cost-only projects surface with ingresos_eur=0.

DROP VIEW IF EXISTS v_project_roi;
CREATE VIEW v_project_roi AS
WITH value_agg AS (
    SELECT project,
           ROUND(SUM(CASE WHEN tipo IN ('fee_cobrado','hito_entregado') THEN importe_eur ELSE 0 END), 2) AS ingresos_eur
    FROM project_value GROUP BY project
),
tech_agg AS (
    SELECT project, ROUND(SUM(cost_usd), 4) AS cost_usd_technical
    FROM v_project_cost_weekly GROUP BY project
),
human_agg AS (
    SELECT project,
           ROUND(SUM((julianday(COALESCE(ended_at, datetime('now'))) - julianday(started_at)) * 24.0), 2) AS human_hours
    FROM human_hours GROUP BY project
),
infra_agg AS (
    SELECT project, ROUND(SUM(infra_cost_eur), 2) AS infra_cost_eur
    FROM v_infra_cost_weekly GROUP BY project
),
rate AS (
    SELECT rate_eur_hour FROM labor_rates ORDER BY effective_date DESC, id DESC LIMIT 1
),
all_projects AS (
    SELECT project FROM value_agg
    UNION SELECT project FROM human_agg
    UNION SELECT project FROM infra_agg
)
SELECT
    all_projects.project,
    COALESCE(value_agg.ingresos_eur, 0) AS ingresos_eur,
    COALESCE(tech_agg.cost_usd_technical, 0) AS coste_tecnico_usd_informativo,
    COALESCE(human_agg.human_hours, 0) AS human_hours,
    ROUND(COALESCE(human_agg.human_hours, 0) * (SELECT rate_eur_hour FROM rate), 2) AS coste_humano_eur,
    COALESCE(infra_agg.infra_cost_eur, 0) AS coste_infra_eur,
    ROUND(COALESCE(value_agg.ingresos_eur, 0)
          - (COALESCE(human_agg.human_hours, 0) * (SELECT rate_eur_hour FROM rate))
          - COALESCE(infra_agg.infra_cost_eur, 0), 2) AS roi_eur
FROM all_projects
LEFT JOIN value_agg ON value_agg.project = all_projects.project
LEFT JOIN tech_agg ON tech_agg.project = all_projects.project
LEFT JOIN human_agg ON human_agg.project = all_projects.project
LEFT JOIN infra_agg ON infra_agg.project = all_projects.project;

DROP VIEW IF EXISTS v_budget_deviation;
CREATE VIEW v_budget_deviation AS
WITH cost_agg AS (
    SELECT project,
           ROUND(SUM((julianday(COALESCE(ended_at, datetime('now'))) - julianday(started_at)) * 24.0), 2) AS human_hours
    FROM human_hours GROUP BY project
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

INSERT INTO schema_migrations (version, applied_at)
VALUES ('2026-08-13_roi_views_fix', datetime('now'));
