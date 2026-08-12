-- Stage 8.4: project-level status ('activo'/'pausado'/'entregado'/'abandonado'),
-- read/written for the currently-open project_context row(s) per project
-- (see /root/.claude/plans/distributed-wobbling-gem.md decision 4).

ALTER TABLE project_context
  ADD COLUMN status TEXT NOT NULL DEFAULT 'activo'
  CHECK (status IN ('activo','pausado','entregado','abandonado'));

INSERT INTO schema_migrations (version, applied_at)
VALUES ('2026-08-13_project_context_status', datetime('now'));
