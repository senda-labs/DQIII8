-- Defensively drop the 5 dependent views first, regardless of whether
-- 2026-08-13_roi_views.down.sql / 2026-08-13_roi_views_fix.down.sql have
-- already been run: without this, running this file first orphans the
-- views (SELECT * FROM v_project_roi errors "no such table: project_value").
-- The plan never specified a required down-migration order — this makes
-- the order not matter (disaster-scenario fix, 2026-08-12).
DROP VIEW IF EXISTS v_project_roi;
DROP VIEW IF EXISTS v_budget_deviation;
DROP VIEW IF EXISTS v_infra_cost_weekly;
DROP VIEW IF EXISTS v_context_fragmentation;
DROP VIEW IF EXISTS v_rework_signal;

DROP TABLE IF EXISTS labor_rates;
DROP TABLE IF EXISTS infra_costs;
DROP TABLE IF EXISTS project_budget;
DROP TABLE IF EXISTS project_value;

DELETE FROM schema_migrations WHERE version = '2026-08-13_project_value_and_budget';
DELETE FROM schema_migrations WHERE version = '2026-08-13_roi_views';
DELETE FROM schema_migrations WHERE version = '2026-08-13_roi_views_fix';
DELETE FROM schema_migrations WHERE version = '2026-08-13_infra_cost_weekly_null_fix';
