DROP VIEW IF EXISTS v_rework_signal;
DROP VIEW IF EXISTS v_budget_deviation;
DROP VIEW IF EXISTS v_context_fragmentation;
DROP VIEW IF EXISTS v_project_roi;
DROP VIEW IF EXISTS v_infra_cost_weekly;

DELETE FROM schema_migrations WHERE version = '2026-08-13_roi_views';
