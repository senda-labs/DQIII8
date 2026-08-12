-- jarvis-control3 v2 — human_pending_events (append-only ledger)
-- Diseño: my-projects/jarvis-control3/architecture/07-durable-worker.md
-- Idempotente: CREATE ... IF NOT EXISTS. Aditiva (no dropea nada).
-- Doble anclaje: este DDL debe coincidir con el bloque human_pending_events
-- añadido a database/schema_v2.sql (SSOT para instalación limpia).
-- Nota: get_db() no activa PRAGMA foreign_keys=ON; el FK no se aplica en runtime
-- (la fila-tarea siempre se inserta antes que cualquiera de sus eventos).

BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS human_pending_events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES human_pending_tasks(id),
    ts      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    event   TEXT NOT NULL,          -- 'inserted'|'notify_attempt'|'notify_ok'|'notify_failed'|'status_update_failed'|'reconciled'|'poller_exhausted'|'resolved_by_user'
    detail  TEXT                    -- JSON: {attempt, error, message_id, ...} sin secretos/payload crudo
);

CREATE INDEX IF NOT EXISTS ix_hpt_events_task ON human_pending_events(task_id, ts);

INSERT INTO schema_migrations (version, applied_at)
VALUES ('2026-07-02_human_pending_events', strftime('%Y-%m-%dT%H:%M:%SZ','now'))
ON CONFLICT(version) DO NOTHING;

COMMIT;
