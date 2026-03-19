-- Convergence metrics: iteration, SSIM trend, permission autonomy
ALTER TABLE code_metrics ADD COLUMN iteration_number INTEGER;
ALTER TABLE code_metrics ADD COLUMN ssim_trend TEXT;
ALTER TABLE code_metrics ADD COLUMN best_ssim_so_far REAL;
ALTER TABLE code_metrics ADD COLUMN permission_denials INTEGER DEFAULT 0;
ALTER TABLE code_metrics ADD COLUMN permission_approvals INTEGER DEFAULT 0;
ALTER TABLE code_metrics ADD COLUMN escalations_needed INTEGER DEFAULT 0;
ALTER TABLE code_metrics ADD COLUMN prompt_version INTEGER DEFAULT 1;
ALTER TABLE code_metrics ADD COLUMN groq_model_used TEXT;

-- Visual convergence view per project
CREATE VIEW IF NOT EXISTS visual_convergence AS
SELECT
    project,
    model_tier,
    renderer,
    COUNT(*) AS total_iterations,
    MIN(ssim_score) AS worst_ssim,
    MAX(ssim_score) AS best_ssim,
    ROUND(MAX(ssim_score) - MIN(ssim_score), 4) AS ssim_improvement,
    ssim_trend,
    MIN(CASE WHEN ssim_score > 0.3 THEN iteration_number END)
        AS cycles_to_good_quality
FROM code_metrics
WHERE ssim_score IS NOT NULL
GROUP BY project, model_tier, renderer
ORDER BY best_ssim DESC;

-- Autonomy view per tier
CREATE VIEW IF NOT EXISTS autonomy_score AS
SELECT
    model_tier,
    COUNT(*) AS total_objectives,
    SUM(permission_approvals) AS total_approvals,
    SUM(permission_denials) AS total_denials,
    SUM(escalations_needed) AS total_escalations,
    ROUND(
        100.0 * SUM(permission_approvals) /
        NULLIF(SUM(permission_approvals) + SUM(permission_denials), 0)
    , 1) AS approval_rate_pct,
    ROUND(
        100.0 * SUM(CASE WHEN escalations_needed = 0 THEN 1 ELSE 0 END)
        / COUNT(*), 1
    ) AS zero_escalation_pct
FROM code_metrics
GROUP BY model_tier
ORDER BY zero_escalation_pct DESC;
