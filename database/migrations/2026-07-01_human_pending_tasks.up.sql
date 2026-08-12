-- jarvis-control3 v2 — human_pending_tasks + resumable_actions + schema_migrations
-- Diseño: my-projects/jarvis-control3/architecture/02-data-model.md, 09-state-machine-triggers.md
-- Requiere: PRAGMA foreign_keys=ON en la conexión que ejecuta esto.
-- Idempotente: todos los CREATE usan IF NOT EXISTS.
-- Doble anclaje: este DDL debe coincidir con el bloque human_pending_tasks/resumable_actions
-- añadido a database/schema_v2.sql (SSOT para instalación limpia).

BEGIN TRANSACTION;

-- 1) resumable_actions PRIMERO (destino FK de human_pending_tasks.action_id)
CREATE TABLE IF NOT EXISTS resumable_actions (
  action_id           TEXT PRIMARY KEY,
  kind                TEXT NOT NULL CHECK(kind IN ('standalone_script','claude_agent')),
  entrypoint          TEXT NOT NULL,
  arg_schema          TEXT NOT NULL,
  requires_checkpoint INTEGER NOT NULL DEFAULT 0,
  enabled             INTEGER NOT NULL DEFAULT 1
);

-- 2) human_pending_tasks
CREATE TABLE IF NOT EXISTS human_pending_tasks (
  id                  TEXT PRIMARY KEY,
  dedup_key           TEXT NOT NULL,
  schema_version      INTEGER NOT NULL DEFAULT 2,

  project             TEXT NOT NULL CHECK(project IN ('football-value','intl-reports','hostkey','pokemon-genesis-chaos')),
  action_id           TEXT NOT NULL REFERENCES resumable_actions(action_id),
  blocking_type       TEXT NOT NULL CHECK(blocking_type IN ('captcha','login','2fa','ip_ban','rate_limit','manual_review','other')),
  description         TEXT NOT NULL CHECK(length(description) <= 500),
  target_url          TEXT,
  screenshot_ref      TEXT,
  priority            INTEGER NOT NULL DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),

  resume_args         TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(resume_args) AND length(resume_args) <= 4096),
  checkpoint_ref       TEXT,
  secret_ref           TEXT,
  payload_hash          TEXT NOT NULL,

  created_by            TEXT NOT NULL,
  origin_host            TEXT NOT NULL CHECK(origin_host IN ('netcup','hostinger','windows')),
  origin_pid             INTEGER,
  origin_run_id          TEXT,
  allowed_chat_id        TEXT NOT NULL,
  resolved_by            TEXT,
  resolution_outcome     TEXT CHECK(resolution_outcome IN ('resumed_ok','resumed_failed','manual','discarded','expired_auto') OR resolution_outcome IS NULL),

  status                 TEXT NOT NULL DEFAULT 'pending'
                         CHECK(status IN ('pending','notified','unblocked','claimed','resuming','completed','failed','expired','cancelled')),
  claimed_by             TEXT,
  lease_until            TEXT,
  version                INTEGER NOT NULL DEFAULT 0,

  notified_at            TEXT,
  notify_count           INTEGER NOT NULL DEFAULT 0,
  notification_msg_id    TEXT,

  attempts               INTEGER NOT NULL DEFAULT 0,
  max_attempts            INTEGER NOT NULL DEFAULT 3,
  next_retry_at          TEXT,
  last_error              TEXT,

  created_at             TEXT NOT NULL,
  updated_at             TEXT NOT NULL,
  expires_at             TEXT NOT NULL,
  session_deadline       TEXT,
  resolved_at            TEXT,

  is_test                 INTEGER NOT NULL DEFAULT 0,
  archived                INTEGER NOT NULL DEFAULT 0,

  CHECK ( (status IN ('completed','failed','expired','cancelled')) = (resolved_at IS NOT NULL) )
);

-- 3) schema_migrations (bootstrap + registro de esta migración)
CREATE TABLE IF NOT EXISTS schema_migrations (
  version     TEXT PRIMARY KEY,
  applied_at  TEXT NOT NULL
);

-- 4) Índices parciales
CREATE UNIQUE INDEX IF NOT EXISTS ux_pending_dedup ON human_pending_tasks(dedup_key)
    WHERE status IN ('pending','notified','unblocked','claimed','resuming');
CREATE INDEX IF NOT EXISTS ix_poll   ON human_pending_tasks(status, project) WHERE archived = 0;
CREATE INDEX IF NOT EXISTS ix_expiry ON human_pending_tasks(expires_at)      WHERE status IN ('pending','notified','unblocked');

-- 5) Trigger: máquina de estados aplicada (rechaza transiciones fuera del grafo válido)
CREATE TRIGGER IF NOT EXISTS trg_hpt_valid_transition
BEFORE UPDATE OF status ON human_pending_tasks
FOR EACH ROW
WHEN NOT (
  (OLD.status = 'pending'   AND NEW.status IN ('notified','expired','cancelled')) OR
  (OLD.status = 'notified'  AND NEW.status IN ('unblocked','expired','cancelled')) OR
  (OLD.status = 'unblocked' AND NEW.status IN ('claimed','expired','cancelled')) OR
  (OLD.status = 'claimed'   AND NEW.status IN ('resuming','failed','expired','cancelled')) OR
  (OLD.status = 'resuming'  AND NEW.status IN ('completed','failed')) OR
  (OLD.status = 'failed'    AND NEW.status IN ('claimed','expired','cancelled')) OR
  (OLD.status = NEW.status)
)
BEGIN
  SELECT RAISE(ABORT, 'invalid status transition');
END;

-- 6) Trigger: inmutabilidad de campos de ejecución tras INSERT (anti-tamper estructural)
CREATE TRIGGER IF NOT EXISTS trg_hpt_immutable_exec_fields
BEFORE UPDATE OF action_id, resume_args, checkpoint_ref, payload_hash ON human_pending_tasks
FOR EACH ROW
WHEN NEW.action_id IS NOT OLD.action_id
  OR NEW.resume_args IS NOT OLD.resume_args
  OR NEW.checkpoint_ref IS NOT OLD.checkpoint_ref
  OR NEW.payload_hash IS NOT OLD.payload_hash
BEGIN
  SELECT RAISE(ABORT, 'execution fields are immutable after insert');
END;

INSERT INTO schema_migrations (version, applied_at)
VALUES ('2026-07-01_human_pending_tasks', strftime('%Y-%m-%dT%H:%M:%SZ','now'))
ON CONFLICT(version) DO NOTHING;

COMMIT;
