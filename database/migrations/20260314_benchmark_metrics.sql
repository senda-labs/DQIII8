-- Code metrics per renderer
CREATE TABLE IF NOT EXISTS code_metrics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT DEFAULT (datetime('now')),
    project         TEXT NOT NULL,
    model_tier      TEXT NOT NULL,
    renderer        TEXT NOT NULL,  -- mandelbrot|julia|perlin|cpp|compositor
    objective_id    TEXT,

    -- CODE DENSITY
    lines_of_code       INTEGER,    -- total lines in file
    lines_functional    INTEGER,    -- lines excluding comments and blanks
    cyclomatic_complexity INTEGER,  -- cyclomatic complexity

    -- COMPUTATIONAL EFFICIENCY
    cpu_seconds         REAL,       -- render time in seconds
    memory_peak_mb      REAL,       -- RAM peak via tracemalloc
    megapixels          REAL,       -- pixels generated in millions
    cpu_per_megapixel   REAL,       -- cpu_seconds / megapixels

    -- CODE QUALITY
    uses_vectorization  INTEGER,    -- 1 if using numpy vectorized, 0 if loops
    uses_numpy_only     INTEGER,    -- 1 if no Python loops
    has_type_hints      INTEGER,    -- 1 if has type hints
    passes_tests        INTEGER,    -- 1 if pytest passes

    -- VISUAL QUALITY
    ssim_score          REAL,       -- similarity vs reference image
    ssim_quality        TEXT,       -- excellent|good|partial|poor
    output_variance     REAL,       -- pixel variance (not a black image)
    contrast_ratio      REAL,       -- output contrast

    -- C++ SPECIFIC
    speedup_vs_python   REAL,       -- C++ / Python speed ratio
    uses_simd           INTEGER,    -- 1 if using SSE/AVX intrinsics
    compiled_ok         INTEGER,    -- 1 if gcc compiled without errors

    -- FINAL RESULT
    success             INTEGER,    -- 1 if all criteria met
    failure_reason      TEXT        -- why it failed if success=0
);

-- Indexes for fast analysis
CREATE INDEX IF NOT EXISTS idx_code_metrics_tier
    ON code_metrics(model_tier, renderer);
CREATE INDEX IF NOT EXISTS idx_code_metrics_project
    ON code_metrics(project, timestamp);

-- Vista comparativa de tiers
CREATE VIEW IF NOT EXISTS tier_comparison AS
SELECT
    model_tier,
    renderer,
    COUNT(*)                              AS total_runs,
    ROUND(AVG(lines_of_code), 0)          AS avg_lines,
    ROUND(AVG(cpu_seconds), 2)            AS avg_cpu_s,
    ROUND(AVG(memory_peak_mb), 1)         AS avg_ram_mb,
    ROUND(AVG(cpu_per_megapixel), 3)      AS avg_cpu_per_mpx,
    ROUND(AVG(ssim_score), 4)             AS avg_ssim,
    ROUND(AVG(speedup_vs_python), 2)      AS avg_cpp_speedup,
    SUM(uses_vectorization)               AS vectorized_count,
    SUM(passes_tests)                     AS tests_passed,
    ROUND(100.0 * SUM(success) / COUNT(*), 1) AS success_rate_pct
FROM code_metrics
GROUP BY model_tier, renderer
ORDER BY model_tier, renderer;

-- Vista de ranking global por tier
CREATE VIEW IF NOT EXISTS tier_ranking AS
SELECT
    model_tier,
    COUNT(DISTINCT renderer)              AS renderers_completed,
    ROUND(AVG(lines_of_code), 0)          AS avg_lines_per_renderer,
    ROUND(AVG(cpu_seconds), 2)            AS avg_render_time_s,
    ROUND(AVG(memory_peak_mb), 1)         AS avg_memory_mb,
    ROUND(AVG(ssim_score), 4)             AS avg_visual_quality,
    ROUND(AVG(speedup_vs_python), 2)      AS avg_cpp_speedup,
    ROUND(100.0 * SUM(success) / COUNT(*), 1) AS overall_success_pct,
    -- Score compuesto (0-100)
    ROUND(
        (100.0 * SUM(success) / COUNT(*)) * 0.35 +
        -- Code efficiency: fewer lines = better (normalized to 100)
        (100.0 - MIN(100, AVG(lines_of_code) / 2.0)) * 0.20 +
        -- Velocidad: <30s target
        (100.0 - MIN(100, AVG(cpu_seconds) / 0.3)) * 0.20 +
        -- Calidad visual SSIM
        (COALESCE(AVG(ssim_score), 0) * 100) * 0.25
    , 1) AS composite_score
FROM code_metrics
GROUP BY model_tier
ORDER BY composite_score DESC;
