-- JARVIS — jarvis_metrics.db schema
-- Patch 3: WAL mode + índices para concurrencia y velocidad del auditor

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ── Cada acción de cada agente ──────────────────────────────────
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
    blocked_by_hook INTEGER DEFAULT 0
);

-- ── Errores con keywords (análisis de causa raíz) ───────────────
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
    lesson_added    INTEGER DEFAULT 0
);

-- ── Resumen por sesión ──────────────────────────────────────────
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
    clear_contexts      INTEGER DEFAULT 0
);

-- ── Performance de skills ───────────────────────────────────────
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

-- ── Reportes del agente auditor ─────────────────────────────────
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

-- ── Patch 3: índices ────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_actions_agent   ON agent_actions(agent_name, timestamp);
CREATE INDEX IF NOT EXISTS idx_actions_session ON agent_actions(session_id);
CREATE INDEX IF NOT EXISTS idx_actions_success ON agent_actions(success, timestamp);
CREATE INDEX IF NOT EXISTS idx_errors_session  ON error_log(session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_proj   ON sessions(project, start_time);

-- ── Vistas para el auditor ──────────────────────────────────────
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

-- ── PermissionAnalyzer v2 — Historial de decisiones de permisos ─────────────
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
