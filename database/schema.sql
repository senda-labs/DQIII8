-- JARVIS — jarvis_metrics.db schema
-- Patch 3: WAL mode + indexes for concurrency and auditor speed

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ── Every action of every agent ─────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_actions (
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
    blocked_by_hook INTEGER DEFAULT 0,
    cost_eur        REAL    DEFAULT 0.0,
    model_tier      INTEGER DEFAULT 0,
    tokens_input    INTEGER DEFAULT 0,
    tokens_output   INTEGER DEFAULT 0,
    estimated_cost_usd REAL DEFAULT 0.0,
    tier            TEXT    DEFAULT 'unknown',
    domain_enriched BOOLEAN DEFAULT 0,
    domain          TEXT,
    knowledge_chunks_used INTEGER DEFAULT 0,
    energy_wh       REAL    DEFAULT 0,     -- Phase 3+4
    cpu_percent     REAL    DEFAULT 0      -- Phase 3+4
);

-- ── Errors with keywords (root cause analysis) ──────────────────
CREATE TABLE IF NOT EXISTS error_log (
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
    lesson_added    INTEGER DEFAULT 0,
    action_id       INTEGER REFERENCES agent_actions(id)
);

-- ── Session summary ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
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
    clear_contexts      INTEGER DEFAULT 0,
    compact_count       INTEGER DEFAULT 0
);

-- ── Skill performance ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS skill_metrics (
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

-- ── Auditor agent reports ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_reports (
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

-- ── Instincts (Continuous Learning v2) ─────────────────────────
CREATE TABLE IF NOT EXISTS instincts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword         TEXT NOT NULL,
    pattern         TEXT NOT NULL,
    confidence      REAL DEFAULT 0.5,
    times_applied   INTEGER DEFAULT 0,
    times_successful INTEGER DEFAULT 0,
    source          TEXT,               -- lessons.md | manual
    project         TEXT,               -- project scope, NULL=global
    created_at      TEXT,
    last_applied    TEXT
);

CREATE INDEX IF NOT EXISTS idx_instincts_keyword ON instincts(keyword);
CREATE INDEX IF NOT EXISTS idx_instincts_project ON instincts(project, confidence);

-- ── Patch 3: indexes ────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_actions_agent   ON agent_actions(agent_name, timestamp);
CREATE INDEX IF NOT EXISTS idx_actions_session ON agent_actions(session_id);
CREATE INDEX IF NOT EXISTS idx_actions_success ON agent_actions(success, timestamp);
CREATE INDEX IF NOT EXISTS idx_errors_session  ON error_log(session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_proj   ON sessions(project, start_time);

-- ── Views for auditor ───────────────────────────────────────────
CREATE VIEW IF NOT EXISTS agent_performance AS
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
ORDER BY success_rate_pct DESC;

CREATE VIEW IF NOT EXISTS error_keywords_freq AS
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
ORDER BY frequency DESC;

-- ── PermissionAnalyzer v2 — Permission decision history ──────────────────────
CREATE TABLE IF NOT EXISTS permission_decisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL DEFAULT (datetime('now')),
    session_id      TEXT    NOT NULL,
    tool_name       TEXT    NOT NULL,
    action_detail   TEXT,
    decision        TEXT    NOT NULL,   -- APPROVE | DENY | ESCALATE
    reason          TEXT,
    risk_level      TEXT,               -- LOW | MEDIUM | HIGH | CRITICAL
    rule_triggered  TEXT,
    suggested_fix   TEXT
);

CREATE INDEX IF NOT EXISTS idx_perm_session_tool
    ON permission_decisions(session_id, tool_name, decision, timestamp);

-- ── OrchestratorLoop — Project objectives ───────────────────────────────────
CREATE TABLE IF NOT EXISTS objectives (
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
);

CREATE INDEX IF NOT EXISTS idx_objectives_project_status
    ON objectives(project, status);

-- ── PermissionAnalyzer — Learned safe patterns ──────────────────────────────
CREATE TABLE IF NOT EXISTS learned_approvals (
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

CREATE INDEX IF NOT EXISTS idx_learned_approvals_tool
    ON learned_approvals(tool_name, active);

-- ── OrchestratorLoop — Effectiveness by project ────────────────────────────
CREATE VIEW IF NOT EXISTS loop_effectiveness AS
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
GROUP BY project;

-- ── Multi-Tier Benchmark — Results by model ─────────────────────────────────
-- ── Intent Amplification log ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS amplification_log (
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
    elapsed_ms      INTEGER,
    confidence      REAL    DEFAULT 0,    -- Phase 3+4
    knowledge_used  INTEGER DEFAULT 0,    -- Phase 3+4
    subtask_count   INTEGER DEFAULT 0,    -- Phase 3+4
    success         INTEGER DEFAULT 1     -- Phase 3+4
);

-- ── Vault memory (semantic triple store) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS vault_memory (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    subject     TEXT NOT NULL,
    predicate   TEXT NOT NULL,
    object      TEXT NOT NULL,
    project     TEXT DEFAULT '',
    confidence  REAL DEFAULT 1.0,
    times_seen  INTEGER DEFAULT 1,
    source      TEXT DEFAULT 'session_stop',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen   TEXT NOT NULL DEFAULT (datetime('now')),
    entry_type  TEXT DEFAULT 'lesson' CHECK(entry_type IN ('adr','project_state','lesson','checkpoint')),
    decay_score REAL DEFAULT 1.0,
    last_accessed TEXT,
    access_count  INTEGER DEFAULT 0,
    scope         TEXT DEFAULT 'session',
    embedding     BLOB,
    transferable  INTEGER DEFAULT 0,
    UNIQUE(subject, predicate, object)
);

-- ── Domain enrichment (Intent Amplifier centroid cache) ───────────────────
CREATE TABLE IF NOT EXISTS domain_enrichment (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    description TEXT    NOT NULL,
    keywords    TEXT    NOT NULL,  -- JSON array
    centroid    BLOB,              -- packed float32 embedding
    created_at  TEXT    DEFAULT (datetime('now')),
    updated_at  TEXT    DEFAULT (datetime('now'))
);

-- ── Learning metrics (per-session aggregate) ──────────────────────────────
CREATE TABLE IF NOT EXISTS learning_metrics (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        TEXT,
    timestamp         DATETIME DEFAULT CURRENT_TIMESTAMP,
    lessons_auto      INTEGER DEFAULT 0,
    lessons_manual    INTEGER DEFAULT 0,
    patterns_detected INTEGER DEFAULT 0
);

CREATE VIEW IF NOT EXISTS benchmark_results AS
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
    ), 0)                                                              AS avg_duration_s
FROM objectives
WHERE model_tier IS NOT NULL
GROUP BY model_tier, project
ORDER BY success_rate_pct DESC;
