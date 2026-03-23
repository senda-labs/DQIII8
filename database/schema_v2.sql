CREATE TABLE agent_actions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL DEFAULT (datetime('now')),
    session_id      TEXT    NOT NULL,
    agent_name      TEXT    NOT NULL,
    project         TEXT,
    tool_used       TEXT,
    file_path       TEXT,
    action_type     TEXT,               -- edit|read|bash|search|write
    start_time_ms   INTEGER,
    end_time_ms     INTEGER,
    duration_ms     INTEGER,
    model_used      TEXT,               -- qwen3b | claude-sonnet
    tokens_used     INTEGER,
    success         INTEGER DEFAULT 1,  -- 1=OK  0=ERROR
    error_message   TEXT,
    bytes_written   INTEGER DEFAULT 0,
    files_modified  TEXT,               -- JSON array
    worktree        TEXT,
    skills_active   TEXT,               -- JSON array
    blocked_by_hook INTEGER DEFAULT 0
, cost_eur REAL DEFAULT 0.0, model_tier INTEGER DEFAULT 0, tokens_input INTEGER DEFAULT 0, tokens_output INTEGER DEFAULT 0, estimated_cost_usd REAL DEFAULT 0.0, tier TEXT DEFAULT 'unknown', domain_enriched BOOLEAN DEFAULT 0, domain TEXT, knowledge_chunks_used INTEGER DEFAULT 0, energy_wh REAL DEFAULT 0, cpu_percent REAL DEFAULT 0);
CREATE TABLE error_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL DEFAULT (datetime('now')),
    session_id      TEXT    NOT NULL,
    agent_name      TEXT    NOT NULL,
    error_type      TEXT    NOT NULL,
    error_message   TEXT    NOT NULL,
    keywords        TEXT,               -- JSON: ["windows-path","encoding"]
    cause           TEXT,
    resolution      TEXT,
    resolved        INTEGER DEFAULT 0,
    resolution_ms   INTEGER,
    lesson_added    INTEGER DEFAULT 0
, action_id INTEGER REFERENCES agent_actions(id));
CREATE TABLE sessions (
    session_id          TEXT PRIMARY KEY,
    start_time          TEXT NOT NULL DEFAULT (datetime('now')),
    end_time            TEXT,
    project             TEXT,
    model_used          TEXT,
    total_actions       INTEGER DEFAULT 0,
    total_errors        INTEGER DEFAULT 0,
    errors_resolved     INTEGER DEFAULT 0,
    total_tokens        INTEGER DEFAULT 0,
    total_duration_ms   INTEGER DEFAULT 0,
    files_touched       INTEGER DEFAULT 0,
    bytes_written       INTEGER DEFAULT 0,
    worktrees_used      INTEGER DEFAULT 0,
    skills_loaded       TEXT,           -- JSON array
    agents_used         TEXT,           -- JSON array
    lessons_added       INTEGER DEFAULT 0,
    clear_contexts      INTEGER DEFAULT 0
, compact_count INTEGER DEFAULT 0);
CREATE TABLE skill_metrics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_name      TEXT NOT NULL,
    timestamp       TEXT NOT NULL DEFAULT (datetime('now')),
    project         TEXT,
    times_loaded    INTEGER DEFAULT 0,
    avg_duration_ms REAL,
    success_rate    REAL,
    errors_caused   INTEGER DEFAULT 0,
    tokens_consumed INTEGER DEFAULT 0,
    approved_by     TEXT DEFAULT 'pending',  -- user|ai|both|pending
    approved_date   TEXT,
    last_reviewed   TEXT,
    source_repo     TEXT,
    review_notes    TEXT
);
CREATE TABLE audit_reports (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp           TEXT NOT NULL DEFAULT (datetime('now')),
    period_start        TEXT,
    period_end          TEXT,
    report_path         TEXT,
    sessions_analyzed   INTEGER,
    total_actions       INTEGER,
    global_success_rate REAL,
    top_error_keywords  TEXT,           -- JSON array
    worst_agent         TEXT,
    best_agent          TEXT,
    worst_skill         TEXT,
    recommendations     TEXT,           -- JSON array
    overall_score       REAL
);
CREATE INDEX idx_actions_agent   ON agent_actions(agent_name, timestamp);
CREATE INDEX idx_actions_session ON agent_actions(session_id);
CREATE INDEX idx_actions_success ON agent_actions(success, timestamp);
CREATE INDEX idx_errors_session  ON error_log(session_id);
CREATE INDEX idx_sessions_proj   ON sessions(project, start_time);
CREATE VIEW agent_performance AS
SELECT
    agent_name,
    COUNT(*)                                               AS total_actions,
    ROUND(AVG(success) * 100, 1)                           AS success_rate_pct,
    ROUND(AVG(duration_ms), 0)                             AS avg_duration_ms,
    SUM(bytes_written)                                     AS total_bytes_written,
    SUM(CASE WHEN blocked_by_hook=1 THEN 1 ELSE 0 END)    AS times_blocked,
    MAX(timestamp)                                         AS last_active
FROM agent_actions
GROUP BY agent_name
ORDER BY success_rate_pct DESC
/* agent_performance(agent_name,total_actions,success_rate_pct,avg_duration_ms,total_bytes_written,times_blocked,last_active) */;
CREATE VIEW error_keywords_freq AS
SELECT
    je.value                                               AS keyword,
    COUNT(*)                                               AS frequency,
    MIN(e.timestamp)                                       AS first_seen,
    MAX(e.timestamp)                                       AS last_seen,
    ROUND(AVG(e.resolution_ms) / 1000.0, 1)               AS avg_resolution_secs,
    SUM(CASE WHEN e.resolved=1 THEN 1 ELSE 0 END)         AS times_resolved
FROM error_log e, json_each(e.keywords) je
WHERE e.keywords IS NOT NULL AND e.keywords != '[]'
GROUP BY je.value
ORDER BY frequency DESC
/* error_keywords_freq(keyword,frequency,first_seen,last_seen,avg_resolution_secs,times_resolved) */;
CREATE TABLE agent_registry (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id     TEXT NOT NULL,
    agent_type   TEXT NOT NULL,
    parent_session TEXT,
    start_time   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_registry_agent ON agent_registry(agent_id);
CREATE TABLE jal_objectives (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    objective_id        TEXT UNIQUE NOT NULL,
    title               TEXT NOT NULL,
    description         TEXT,
    type                TEXT DEFAULT 'general',
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    started_at          TEXT,
    completed_at        TEXT,
    status              TEXT DEFAULT 'queue',
    priority            INTEGER DEFAULT 5,
    max_attempts        INTEGER DEFAULT 3,
    current_attempt     INTEGER DEFAULT 0,
    score_final         REAL DEFAULT 0.0,
    score_raw           REAL DEFAULT 0.0,
    entropy_H           REAL DEFAULT 0.0,
    passed              INTEGER DEFAULT 0,
    iker_approved       INTEGER DEFAULT 0,
    lessons_count       INTEGER DEFAULT 0,
    tags                TEXT
);
CREATE TABLE jal_steps (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    objective_id    TEXT NOT NULL,
    attempt         INTEGER NOT NULL,
    step_number     INTEGER NOT NULL,
    description     TEXT NOT NULL,
    weight          REAL DEFAULT 0.33,
    criticality     INTEGER DEFAULT 1,
    status          TEXT DEFAULT 'pending',
    started_at      TEXT,
    completed_at    TEXT,
    duration_ms     INTEGER DEFAULT 0,
    completion_pct  REAL DEFAULT 0.0,
    step_score      REAL DEFAULT 0.0,
    result_summary  TEXT,
    error_raw       TEXT,
    error_category  TEXT DEFAULT 'unknown',
    error_severity  INTEGER DEFAULT 0,
    propagation_est REAL DEFAULT 0.0,
    executor        TEXT DEFAULT 'claude_code',
    model_used      TEXT,
    tokens_used     INTEGER DEFAULT 0,
    retry_count     INTEGER DEFAULT 0,
    UNIQUE(objective_id, attempt, step_number)
);
CREATE TABLE jal_scoring_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    objective_id    TEXT NOT NULL,
    attempt         INTEGER NOT NULL,
    evaluated_at    TEXT NOT NULL DEFAULT (datetime('now')),
    evaluator       TEXT DEFAULT 'gemini-2.0-flash',
    score_raw       REAL NOT NULL,
    entropy_H       REAL NOT NULL,
    entropy_penalty REAL NOT NULL,
    blocker_penalty REAL NOT NULL,
    momentum_bonus  REAL NOT NULL,
    score_final     REAL NOT NULL,
    delta_score     REAL DEFAULT 0.0,
    convergence_est REAL,
    converges       INTEGER DEFAULT 0,
    steps_total     INTEGER DEFAULT 0,
    steps_completed INTEGER DEFAULT 0,
    steps_failed    INTEGER DEFAULT 0,
    has_blocker     INTEGER DEFAULT 0,
    breakdown_json  TEXT NOT NULL,
    gemini_raw      TEXT
);
CREATE TABLE jal_error_taxonomy (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    objective_id    TEXT NOT NULL,
    attempt         INTEGER NOT NULL,
    step_number     INTEGER NOT NULL,
    recorded_at     TEXT DEFAULT (datetime('now')),
    error_code      TEXT NOT NULL,
    category        TEXT NOT NULL,
    severity        INTEGER NOT NULL CHECK(severity BETWEEN 1 AND 5),
    propagation     REAL NOT NULL CHECK(propagation BETWEEN 0 AND 1),
    fix_complexity  INTEGER NOT NULL CHECK(fix_complexity BETWEEN 1 AND 5),
    critical_score  REAL NOT NULL,
    priority_label  TEXT NOT NULL,
    error_message   TEXT,
    fix_suggested   TEXT,
    fix_applied     TEXT,
    resolved        INTEGER DEFAULT 0,
    resolved_at     TEXT,
    seen_before     INTEGER DEFAULT 0,
    pattern_id      TEXT
);
CREATE TABLE jal_error_patterns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_id      TEXT UNIQUE NOT NULL,
    first_seen      TEXT DEFAULT (datetime('now')),
    last_seen       TEXT DEFAULT (datetime('now')),
    category        TEXT NOT NULL,
    error_signature TEXT NOT NULL,
    trigger_context TEXT,
    frequency       INTEGER DEFAULT 1,
    total_executions INTEGER DEFAULT 1,
    failure_rate    REAL DEFAULT 1.0,
    avg_propagation REAL DEFAULT 0.0,
    avg_severity    REAL DEFAULT 0.0,
    avg_fix_time_ms INTEGER DEFAULT 0,
    prevention_rule TEXT,
    fix_rule        TEXT,
    prevention_effective INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'active'
);
CREATE TABLE jal_conversations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    objective_id    TEXT NOT NULL,
    message_at      TEXT DEFAULT (datetime('now')),
    direction       TEXT NOT NULL CHECK(direction IN ('out','in')),
    message_text    TEXT NOT NULL,
    intent          TEXT,
    score_at_time   REAL DEFAULT 0.0,
    action_result   TEXT,
    update_id       INTEGER
);
CREATE INDEX idx_steps_obj
    ON jal_steps(objective_id, attempt);
CREATE INDEX idx_errors_category
    ON jal_error_taxonomy(category, severity);
CREATE INDEX idx_patterns_freq
    ON jal_error_patterns(failure_rate DESC, frequency DESC);
CREATE INDEX idx_snapshots_obj
    ON jal_scoring_snapshots(objective_id, attempt);
CREATE VIEW v_claude_reliability AS
SELECT
    o.type                              AS task_type,
    COUNT(DISTINCT o.objective_id)      AS total_objectives,
    SUM(o.passed)                       AS passed,
    ROUND(AVG(o.score_final) * 100, 1)  AS avg_score_pct,
    ROUND(AVG(o.current_attempt), 2)    AS avg_attempts_needed,
    ROUND(AVG(o.entropy_H), 3)          AS avg_entropy,
    ROUND(CAST(SUM(o.passed) AS REAL) /
          NULLIF(COUNT(*), 0) * 100, 1) AS reliability_pct
FROM jal_objectives o
WHERE o.status IN ('completed', 'failed')
GROUP BY o.type
ORDER BY reliability_pct DESC
/* v_claude_reliability(task_type,total_objectives,passed,avg_score_pct,avg_attempts_needed,avg_entropy,reliability_pct) */;
CREATE VIEW v_error_ranking AS
SELECT
    p.pattern_id,
    p.category,
    p.frequency,
    ROUND(p.failure_rate * 100, 1)      AS failure_rate_pct,
    ROUND(p.avg_severity, 2)            AS avg_severity,
    ROUND(p.avg_propagation, 3)         AS avg_propagation,
    p.prevention_rule,
    p.fix_rule,
    p.status,
    ROUND(p.frequency * p.avg_severity *
          p.avg_propagation, 3)         AS danger_index
FROM jal_error_patterns p
ORDER BY danger_index DESC
/* v_error_ranking(pattern_id,category,frequency,failure_rate_pct,avg_severity,avg_propagation,prevention_rule,fix_rule,status,danger_index) */;
CREATE VIEW v_convergence_history AS
SELECT
    s.objective_id,
    s.attempt,
    ROUND(s.score_final * 100, 1)       AS score_pct,
    ROUND(s.delta_score * 100, 1)       AS delta_pct,
    ROUND(s.entropy_H, 3)               AS entropy,
    s.converges,
    s.convergence_est,
    s.has_blocker,
    s.steps_failed
FROM jal_scoring_snapshots s
ORDER BY s.objective_id, s.attempt
/* v_convergence_history(objective_id,attempt,score_pct,delta_pct,entropy,converges,convergence_est,has_blocker,steps_failed) */;
CREATE TABLE video_metrics (id INTEGER PRIMARY KEY AUTOINCREMENT, collected_at TEXT NOT NULL, platform TEXT NOT NULL, channel_id TEXT, channel_name TEXT, video_id TEXT NOT NULL, video_title TEXT, published_at TEXT, duration_s INTEGER, views INTEGER DEFAULT 0, views_24h INTEGER DEFAULT 0, views_7d INTEGER DEFAULT 0, watch_time_hours REAL DEFAULT 0, avg_view_duration_s INTEGER DEFAULT 0, retention_rate REAL DEFAULT 0, likes INTEGER DEFAULT 0, comments INTEGER DEFAULT 0, shares INTEGER DEFAULT 0, ctr REAL DEFAULT 0, rpm REAL DEFAULT 0, estimated_revenue REAL DEFAULT 0, renderer_used TEXT, mode_narrativo TEXT, api_externa TEXT, coste_produccion REAL DEFAULT 0, performance_score REAL DEFAULT 0);
CREATE TABLE channel_stats (id INTEGER PRIMARY KEY AUTOINCREMENT, collected_at TEXT NOT NULL, platform TEXT NOT NULL, channel_id TEXT NOT NULL, channel_name TEXT, subscribers INTEGER DEFAULT 0, total_views INTEGER DEFAULT 0, total_videos INTEGER DEFAULT 0, monthly_revenue REAL DEFAULT 0);
CREATE TABLE platform_config (platform TEXT PRIMARY KEY, channel_id TEXT, channel_name TEXT, api_key_env TEXT, enabled INTEGER DEFAULT 1, last_collected TEXT, notes TEXT);
CREATE INDEX idx_video_platform ON video_metrics(platform, published_at);
CREATE INDEX idx_video_score ON video_metrics(performance_score DESC);
CREATE VIEW top_performing_content AS SELECT mode_narrativo, renderer_used, platform, COUNT(*) AS total_videos, ROUND(AVG(views_7d),0) AS avg_views_7d, ROUND(AVG(retention_rate),2) AS avg_retention, ROUND(AVG(ctr),3) AS avg_ctr, ROUND(AVG(rpm),2) AS avg_rpm, ROUND(AVG(performance_score),1) AS avg_score FROM video_metrics WHERE views > 0 GROUP BY mode_narrativo, renderer_used, platform ORDER BY avg_score DESC
/* top_performing_content(mode_narrativo,renderer_used,platform,total_videos,avg_views_7d,avg_retention,avg_ctr,avg_rpm,avg_score) */;
CREATE VIEW revenue_by_channel AS SELECT platform, channel_name, COUNT(*) AS videos_published, SUM(estimated_revenue) AS total_revenue, ROUND(AVG(rpm),2) AS avg_rpm, SUM(views) AS total_views FROM video_metrics GROUP BY platform, channel_name ORDER BY total_revenue DESC
/* revenue_by_channel(platform,channel_name,videos_published,total_revenue,avg_rpm,total_views) */;
CREATE TABLE instincts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword         TEXT NOT NULL,
    pattern         TEXT NOT NULL,
    confidence      REAL DEFAULT 0.5,
    times_applied   INTEGER DEFAULT 0,
    times_successful INTEGER DEFAULT 0,
    source          TEXT,
    project         TEXT,
    created_at      TEXT,
    last_applied    TEXT
);
CREATE INDEX idx_instincts_keyword ON instincts(keyword);
CREATE INDEX idx_instincts_project ON instincts(project, confidence);
CREATE TABLE permission_decisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL DEFAULT (datetime('now')),
    session_id      TEXT    NOT NULL,
    tool_name       TEXT    NOT NULL,
    action_detail   TEXT,
    decision        TEXT    NOT NULL,
    reason          TEXT,
    risk_level      TEXT,
    rule_triggered  TEXT,
    suggested_fix   TEXT
);
CREATE INDEX idx_perm_session_tool
    ON permission_decisions(session_id, tool_name, decision, timestamp);
CREATE TABLE objectives (
    id               TEXT PRIMARY KEY,   -- UUID corto (8 chars)
    project          TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending',
        -- pending | running | completed | failed | blocked
    objective_text   TEXT NOT NULL,
    success_criteria TEXT,
    context_snapshot TEXT,               -- JSON: estado antes de empezar
    retry_count      INTEGER DEFAULT 0,
    max_retries      INTEGER DEFAULT 3,
    token_usage      INTEGER DEFAULT 0,
    created_at       TEXT NOT NULL,
    started_at       TEXT,
    completed_at     TEXT,
    result_summary   TEXT,               -- JSON: output de capture()
    lessons_added    TEXT,               -- JSON array de lecciones nuevas
    error_message    TEXT
, model_tier TEXT DEFAULT 'tier3', planner_quality TEXT DEFAULT NULL, ssim_score REAL DEFAULT NULL, ssim_quality TEXT DEFAULT NULL);
CREATE INDEX idx_objectives_project_status
    ON objectives(project, status);
CREATE TABLE learned_approvals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project     TEXT NOT NULL DEFAULT '*',
    tool_name   TEXT NOT NULL,
    pattern     TEXT NOT NULL,       -- substrng del action_detail aprobado
    times_seen  INTEGER DEFAULT 1,
    last_seen   TEXT,
    approved_by TEXT DEFAULT 'system',  -- 'system' | 'user'
    active      INTEGER DEFAULT 0,      -- 1 cuando times_seen >= 3
    UNIQUE(tool_name, pattern)
);
CREATE INDEX idx_learned_approvals_tool
    ON learned_approvals(tool_name, active);
CREATE VIEW loop_effectiveness AS
SELECT
    project,
    COUNT(*)                                                          AS total_cycles,
    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END)            AS successful,
    SUM(CASE WHEN status = 'failed'    THEN 1 ELSE 0 END)            AS failed,
    SUM(CASE WHEN status = 'blocked'   THEN 1 ELSE 0 END)            AS escalated,
    ROUND(
        100.0 * SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END)
        / COUNT(*), 1
    )                                                                 AS success_rate_pct,
    MAX(completed_at)                                                 AS last_activity
FROM objectives
GROUP BY project
/* loop_effectiveness(project,total_cycles,successful,failed,escalated,success_rate_pct,last_activity) */;
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
    SUM(CASE WHEN planner_quality = 'poor'    THEN 1 ELSE 0 END)      AS planner_poor,
    ROUND(AVG(ssim_score), 4)                                         AS avg_ssim_score
FROM objectives
WHERE model_tier IS NOT NULL
GROUP BY model_tier, project
ORDER BY success_rate_pct DESC
/* benchmark_results(model_tier,project,total_objectives,completed,failed,blocked,success_rate_pct,avg_duration_s,planner_good,planner_partial,planner_poor,avg_ssim_score) */;
CREATE TABLE code_metrics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT DEFAULT (datetime('now')),
    project         TEXT NOT NULL,
    model_tier      TEXT NOT NULL,
    renderer        TEXT NOT NULL,  -- mandelbrot|julia|perlin|cpp|compositor
    objective_id    TEXT,

    -- DENSIDAD DE CÓDIGO
    lines_of_code       INTEGER,    -- líneas totales del archivo
    lines_functional    INTEGER,    -- líneas sin comentarios ni blancos
    cyclomatic_complexity INTEGER,  -- complejidad ciclomática

    -- EFICIENCIA COMPUTACIONAL
    cpu_seconds         REAL,       -- tiempo de render en segundos
    memory_peak_mb      REAL,       -- RAM peak con tracemalloc
    megapixels          REAL,       -- píxeles generados en millones
    cpu_per_megapixel   REAL,       -- cpu_seconds / megapixels

    -- CALIDAD DEL CÓDIGO
    uses_vectorization  INTEGER,    -- 1 si usa numpy vectorizado, 0 si loops
    uses_numpy_only     INTEGER,    -- 1 si no usa loops Python
    has_type_hints      INTEGER,    -- 1 si tiene type hints
    passes_tests        INTEGER,    -- 1 si pytest pasa

    -- CALIDAD VISUAL
    ssim_score          REAL,       -- similitud con imagen de referencia
    ssim_quality        TEXT,       -- excellent|good|partial|poor
    output_variance     REAL,       -- varianza de píxeles (no es imagen negra)
    contrast_ratio      REAL,       -- contraste del output

    -- C++ ESPECÍFICO
    speedup_vs_python   REAL,       -- ratio velocidad C++ / Python
    uses_simd           INTEGER,    -- 1 si usa SSE/AVX intrinsics
    compiled_ok         INTEGER,    -- 1 si gcc compiló sin errores

    -- RESULTADO FINAL
    success             INTEGER,    -- 1 si cumplió todos los criterios
    failure_reason      TEXT        -- por qué falló si success=0
, prompt_length_tokens INTEGER, attempts_to_success INTEGER DEFAULT 1, first_attempt_success INTEGER DEFAULT 0, self_corrections INTEGER DEFAULT 0, syntax_errors INTEGER DEFAULT 0, import_errors INTEGER DEFAULT 0, constraint_violations INTEGER DEFAULT 0, ssim_delta_vs_prev REAL, color_palette_distance REAL, tokens_input INTEGER, tokens_output INTEGER, estimated_cost_usd REAL, wall_clock_seconds REAL, planning_seconds REAL, execution_seconds REAL, objective_clarity TEXT, iteration_number INTEGER, ssim_trend TEXT, best_ssim_so_far REAL, permission_denials INTEGER DEFAULT 0, permission_approvals INTEGER DEFAULT 0, escalations_needed INTEGER DEFAULT 0, prompt_version INTEGER DEFAULT 1, groq_model_used TEXT);
CREATE INDEX idx_code_metrics_tier
    ON code_metrics(model_tier, renderer);
CREATE INDEX idx_code_metrics_project
    ON code_metrics(project, timestamp);
CREATE VIEW tier_comparison AS
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
ORDER BY model_tier, renderer
/* tier_comparison(model_tier,renderer,total_runs,avg_lines,avg_cpu_s,avg_ram_mb,avg_cpu_per_mpx,avg_ssim,avg_cpp_speedup,vectorized_count,tests_passed,success_rate_pct) */;
CREATE VIEW tier_ranking AS
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
        -- Eficiencia código: menos líneas = mejor (normalizado a 100)
        (100.0 - MIN(100, AVG(lines_of_code) / 2.0)) * 0.20 +
        -- Velocidad: <30s target
        (100.0 - MIN(100, AVG(cpu_seconds) / 0.3)) * 0.20 +
        -- Calidad visual SSIM
        (COALESCE(AVG(ssim_score), 0) * 100) * 0.25
    , 1) AS composite_score
FROM code_metrics
GROUP BY model_tier
ORDER BY composite_score DESC
/* tier_ranking(model_tier,renderers_completed,avg_lines_per_renderer,avg_render_time_s,avg_memory_mb,avg_visual_quality,avg_cpp_speedup,overall_success_pct,composite_score) */;
CREATE VIEW visual_convergence AS
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
ORDER BY best_ssim DESC
/* visual_convergence(project,model_tier,renderer,total_iterations,worst_ssim,best_ssim,ssim_improvement,ssim_trend,cycles_to_good_quality) */;
CREATE VIEW autonomy_score AS
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
ORDER BY zero_escalation_pct DESC
/* autonomy_score(model_tier,total_objectives,total_approvals,total_denials,total_escalations,approval_rate_pct,zero_escalation_pct) */;
CREATE TABLE loop_objectives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT DEFAULT (datetime('now')),
    project TEXT NOT NULL,
    objective_id TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    success_criteria TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    completed_at TEXT,
    attempts INTEGER DEFAULT 0,
    result TEXT
);
CREATE TABLE video_outputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT DEFAULT (datetime('now')),
    topic TEXT,
    mode TEXT,
    language TEXT,
    duration_s INTEGER,
    file_path TEXT,
    file_size_mb REAL,
    renderer_used TEXT,
    tts_chars INTEGER,
    pipeline_ms INTEGER,
    telegram_sent INTEGER DEFAULT 0,
    approved INTEGER DEFAULT -1,
    notes TEXT
);
CREATE TABLE loop_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT DEFAULT (datetime('now')),
    objective_id TEXT,
    error_type TEXT,
    error_message TEXT,
    file TEXT,
    line INTEGER,
    resolved INTEGER DEFAULT 0,
    resolution TEXT
);
CREATE TABLE morning_report (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT DEFAULT (datetime('now')),
    objectives_total INTEGER,
    objectives_done INTEGER,
    objectives_failed INTEGER,
    videos_generated INTEGER,
    videos_sent_telegram INTEGER,
    errors_total INTEGER,
    errors_resolved INTEGER,
    lessons_added INTEGER,
    report_text TEXT,
    sent_to_telegram INTEGER DEFAULT 0
);
CREATE TABLE gemini_audits (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at       TEXT DEFAULT (datetime('now')),
    module           TEXT NOT NULL,
    metric           TEXT NOT NULL,
    report_path      TEXT,
    question         TEXT,
    gemini_response  TEXT,
    issues_found     INTEGER DEFAULT 0,
    issues_resolved  INTEGER DEFAULT 0,
    impact_score     REAL,
    applied_to_code  INTEGER DEFAULT 0,
    notes            TEXT
);
CREATE TABLE github_research (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at        TEXT DEFAULT (datetime('now')),
    search_topic      TEXT NOT NULL,
    repo_full_name    TEXT NOT NULL UNIQUE,
    repo_url          TEXT,
    description       TEXT,
    stars             INTEGER DEFAULT 0,
    forks             INTEGER DEFAULT 0,
    last_updated      TEXT,
    language          TEXT,
    license           TEXT,
    readme_summary    TEXT,
    topics_tags       TEXT,
    applicability_score   REAL DEFAULT 0.0,
    applicability_reason  TEXT,
    stack_match           TEXT,
    integration_effort    TEXT,
    status            TEXT DEFAULT 'pending',
    reviewed_by       TEXT,
    added_to_project  INTEGER DEFAULT 0,
    notes             TEXT
);
CREATE TABLE github_search_sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT DEFAULT (datetime('now')),
    topic        TEXT NOT NULL,
    query_used   TEXT,
    repos_found  INTEGER DEFAULT 0,
    repos_scored INTEGER DEFAULT 0,
    top_repo     TEXT,
    top_score    REAL,
    report_path  TEXT,
    sent_telegram INTEGER DEFAULT 0
);
CREATE TABLE scene_scripts (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at     TEXT    DEFAULT (datetime('now')),
                    topic          TEXT,
                    mode           TEXT,
                    language       TEXT,
                    channel        TEXT,
                    model_used     TEXT,
                    viral_score    REAL,
                    iterations     INTEGER,
                    n_scenes       INTEGER,
                    total_duration REAL,
                    title_hook     TEXT,
                    scenes_json    TEXT,
                    youtube_views  INTEGER DEFAULT 0,
                    youtube_likes  INTEGER DEFAULT 0,
                    retention_pct  REAL    DEFAULT 0,
                    updated_at     TEXT
                );
CREATE TABLE research_cache (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at       TEXT DEFAULT (datetime('now')),
                    topic            TEXT,
                    summary          TEXT,
                    key_facts_json   TEXT,
                    key_dates_json   TEXT,
                    key_names_json   TEXT,
                    key_numbers_json TEXT,
                    sources_json     TEXT,
                    research_method  TEXT,
                    facts_count      INTEGER
                );
CREATE TABLE historical_events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    title               TEXT NOT NULL UNIQUE,
    category            TEXT,
    year                INTEGER,
    location            TEXT,
    description         TEXT,
    key_facts           TEXT,
    viral_hook          TEXT,
    virality_score      REAL DEFAULT 7.0,
    verified            INTEGER DEFAULT 0,
    verification_notes  TEXT,
    exaggeration_ok     INTEGER DEFAULT 1,
    used                INTEGER DEFAULT 0,
    used_at             TEXT,
    job_id              TEXT,
    channel             TEXT,
    created_at          TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_he_used ON historical_events(used, virality_score DESC);
CREATE INDEX idx_he_category ON historical_events(category, used);
CREATE TABLE sync_state (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL UNIQUE,
    last_sync   TEXT,
    last_id     INTEGER DEFAULT 0,
    synced_rows INTEGER DEFAULT 0
);
CREATE TABLE vault_memory (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    subject     TEXT NOT NULL,
    predicate   TEXT NOT NULL,
    object      TEXT NOT NULL,
    project     TEXT DEFAULT '',
    confidence  REAL DEFAULT 1.0,
    times_seen  INTEGER DEFAULT 1,
    source      TEXT DEFAULT 'session_stop',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen   TEXT NOT NULL DEFAULT (datetime('now')), entry_type TEXT DEFAULT 'lesson' CHECK(entry_type IN ('adr','project_state','lesson','checkpoint')), decay_score REAL DEFAULT 1.0, last_accessed TEXT, access_count INTEGER DEFAULT 0, scope TEXT DEFAULT 'session', embedding BLOB, transferable INTEGER DEFAULT 0,
    UNIQUE(subject, predicate, object)
);
CREATE INDEX idx_vault_memory_project
    ON vault_memory(project, last_seen);
CREATE TABLE resource_claims (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    resource    TEXT NOT NULL UNIQUE,      -- file path or logical resource name
    agent       TEXT NOT NULL,             -- agent_name that holds the claim
    session_id  TEXT NOT NULL,
    claimed_at  TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at  TEXT NOT NULL              -- datetime('now', '+30 minutes') on insert
);
CREATE INDEX idx_resource_claims_expires
    ON resource_claims(expires_at);
CREATE TABLE model_satisfaction (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp           TEXT    NOT NULL DEFAULT (datetime('now')),
    session_id          TEXT    NOT NULL,
    model_used          TEXT    NOT NULL,
    task_type           TEXT,                -- código|análisis|escritura|research|pipeline
    task_description    TEXT,                -- truncated to 100 chars
    duration_ms         INTEGER,
    technical_success   INTEGER DEFAULT 1,   -- 1=OK 0=ERROR
    user_satisfaction   INTEGER,             -- 0=no 1=yes NULL=no response
    tier_used           TEXT                 -- tier1|tier2|tier3
);
CREATE INDEX idx_satisfaction_model_type
    ON model_satisfaction(model_used, task_type, user_satisfaction);
CREATE TABLE spc_metrics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    checked_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    session_id  TEXT,
    trigger_id  TEXT,
    triggered   INTEGER NOT NULL DEFAULT 0,
    reason      TEXT,
    priority    TEXT,
    value_num   REAL,
    threshold   REAL
);
CREATE TABLE vault_memory_archive (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    source TEXT,
    last_seen TEXT,
    entry_type TEXT DEFAULT 'fact',
    decay_score REAL DEFAULT 1.0,
    last_accessed TEXT,
    access_count INTEGER DEFAULT 0,
    archived_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE research_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT DEFAULT (datetime('now')),
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    summary TEXT,
    score REAL DEFAULT 0.0,
    status TEXT DEFAULT 'PENDIENTE_TEST',
    test_result TEXT,
    session_id TEXT
);
CREATE TABLE learning_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    lessons_auto INTEGER DEFAULT 0,
    lessons_manual INTEGER DEFAULT 0,
    patterns_detected INTEGER DEFAULT 0
);
CREATE TABLE domain_enrichment (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL UNIQUE,
            description TEXT    NOT NULL,
            keywords    TEXT    NOT NULL,  -- JSON array
            centroid    BLOB,              -- packed float32 embedding
            created_at  TEXT    DEFAULT (datetime('now')),
            updated_at  TEXT    DEFAULT (datetime('now'))
        );
CREATE INDEX idx_domain_name ON domain_enrichment (name);
CREATE TABLE memory_links (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id   INTEGER NOT NULL REFERENCES vault_memory(id) ON DELETE CASCADE,
            target_id   INTEGER NOT NULL REFERENCES vault_memory(id) ON DELETE CASCADE,
            link_type   TEXT    NOT NULL DEFAULT 'related_to',
            strength    REAL    DEFAULT 1.0,
            created_at  TEXT    DEFAULT (datetime('now')),
            UNIQUE(source_id, target_id, link_type)
        );
CREATE INDEX idx_links_source ON memory_links (source_id);
CREATE INDEX idx_links_target ON memory_links (target_id);
CREATE INDEX idx_vault_scope ON vault_memory (scope);
CREATE TABLE amplification_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      TEXT,
    original_prompt TEXT,
    amplified_prompt TEXT,
    action_detected TEXT,
    entity_detected TEXT,
    niche_detected  TEXT,
    intent_pattern  TEXT,
    top_domain      TEXT,
    tier_selected   INTEGER,
    elapsed_ms      INTEGER
, confidence REAL DEFAULT 0, knowledge_used INTEGER DEFAULT 0, subtask_count INTEGER DEFAULT 0, success INTEGER DEFAULT 1, routing_method TEXT DEFAULT 'single', active_centroids_count INTEGER DEFAULT 1, queued_centroids_count INTEGER DEFAULT 0, classification_ms REAL DEFAULT 0);
CREATE TABLE knowledge_benchmark_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now')),
    task_id INTEGER NOT NULL,
    task_text TEXT NOT NULL,
    task_domain TEXT NOT NULL,
    config TEXT NOT NULL,
    model TEXT NOT NULL,
    dq_enabled BOOLEAN NOT NULL,
    knowledge_injected TEXT,
    accuracy_score REAL,
    completeness_score REAL,
    precision_score REAL,
    overall_score REAL,
    tokens_prompt INTEGER,
    tokens_response INTEGER,
    tokens_total INTEGER,
    time_seconds REAL,
    messages_needed INTEGER,
    cost_usd REAL,
    tier_used TEXT,
    escalation_needed BOOLEAN,
    hallucination_count INTEGER DEFAULT 0,
    factual_errors TEXT,
    judge_model TEXT,
    human_verified BOOLEAN DEFAULT 0
);
CREATE VIEW knowledge_benchmark_summary AS
SELECT
    config, model, dq_enabled, task_domain,
    ROUND(AVG(overall_score), 2) as avg_score,
    ROUND(AVG(tokens_total), 0) as avg_tokens,
    ROUND(AVG(time_seconds), 1) as avg_time,
    ROUND(AVG(messages_needed), 1) as avg_messages,
    ROUND(AVG(cost_usd), 4) as avg_cost,
    ROUND(AVG(hallucination_count), 1) as avg_hallucinations,
    COUNT(*) as n_tasks
FROM knowledge_benchmark_results
GROUP BY config, model, dq_enabled, task_domain
/* knowledge_benchmark_summary(config,model,dq_enabled,task_domain,avg_score,avg_tokens,avg_time,avg_messages,avg_cost,avg_hallucinations,n_tasks) */;
CREATE VIEW knowledge_benchmark_dq_uplift AS
SELECT
    b_on.model, b_on.task_domain,
    ROUND(AVG(b_on.overall_score) - AVG(b_off.overall_score), 2) as score_uplift,
    ROUND(AVG(b_off.tokens_total) - AVG(b_on.tokens_total), 0) as tokens_saved,
    ROUND(AVG(b_off.messages_needed) - AVG(b_on.messages_needed), 1) as messages_saved,
    ROUND(AVG(b_off.hallucination_count) - AVG(b_on.hallucination_count), 1) as hallucinations_reduced
FROM knowledge_benchmark_results b_on
JOIN knowledge_benchmark_results b_off
    ON b_on.task_id = b_off.task_id AND b_on.model = b_off.model
WHERE b_on.dq_enabled = 1 AND b_off.dq_enabled = 0
GROUP BY b_on.model, b_on.task_domain
/* knowledge_benchmark_dq_uplift(model,task_domain,score_uplift,tokens_saved,messages_saved,hallucinations_reduced) */;
