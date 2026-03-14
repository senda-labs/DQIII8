-- Migration: add planner_quality column to objectives
-- Applied: 2026-03-14

ALTER TABLE objectives ADD COLUMN planner_quality TEXT DEFAULT NULL;

-- Recreate benchmark_results view with planner quality stats
DROP VIEW IF EXISTS benchmark_results;
CREATE VIEW benchmark_results AS
SELECT
    model_tier,
    project,
    COUNT(*)                                                           AS total_objectives,
    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END)             AS completed,
    SUM(CASE WHEN status = 'failed'    THEN 1 ELSE 0 END)             AS failed,
    SUM(CASE WHEN status = 'blocked'   THEN 1 ELSE 0 END)             AS blocked,
    ROUND(
        100.0 * SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END)
        / COUNT(*), 1
    )                                                                  AS success_rate_pct,
    ROUND(AVG(
        CASE WHEN completed_at IS NOT NULL AND started_at IS NOT NULL
        THEN (julianday(completed_at) - julianday(started_at)) * 86400
        END
    ), 0)                                                              AS avg_duration_s,
    SUM(CASE WHEN planner_quality = 'good'    THEN 1 ELSE 0 END)      AS planner_good,
    SUM(CASE WHEN planner_quality = 'partial' THEN 1 ELSE 0 END)      AS planner_partial,
    SUM(CASE WHEN planner_quality = 'poor'    THEN 1 ELSE 0 END)      AS planner_poor
FROM objectives
WHERE model_tier IS NOT NULL
GROUP BY model_tier, project
ORDER BY success_rate_pct DESC;
