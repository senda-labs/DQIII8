-- Stage 6 (data reconstruction), Open Decision 1 — approved.
-- Data-only migration, no schema change. Not paired with a down.sql: B1's
-- UPDATE is trigger-legal and irreversible by design (agent_actions is
-- append-only; a second UPDATE after end_time_ms is set is blocked), and B2's
-- annotation is likewise a one-way reconciliation note, not a revertible edit.
--
-- B1: close wrapper (action_type='api_call') rows that already carry a real
-- duration_ms but were never given end_time_ms. trigger-legal (end_time_ms is
-- in the close-out allowed-column set while OLD.end_time_ms IS NULL).
--
-- B2: annotate hook-originated rows orphaned by the pre-Stage-0
-- post_tool_use.py import bug (fixed in commit 85139e8, deployed
-- 2026-08-12T18:21:45Z) with error_message only — end_time_ms/duration_ms
-- are deliberately left NULL rather than fabricated. Scoped to
-- timestamp < the Stage-0 deploy time so genuinely in-flight rows opened
-- after the fix are never touched.
--
-- B3 (historical project backfill): not proposed, per plan — served by
-- v_action_project instead.
--
-- Counts are re-taken immediately before running (not the planning-time
-- snapshot of 1,332 / 565) per the panel-pass-2 correction on Stage 6 B1's
-- assert.

BEGIN TRANSACTION;

UPDATE agent_actions
SET end_time_ms = start_time_ms + duration_ms
WHERE action_type = 'api_call'
  AND end_time_ms IS NULL
  AND duration_ms IS NOT NULL;

UPDATE agent_actions
SET error_message = 'reconciled: orphaned by post_tool_use import bug, fixed 85139e8'
WHERE action_type != 'api_call'
  AND end_time_ms IS NULL
  AND duration_ms IS NULL
  AND timestamp < '2026-08-12 18:21:45';

INSERT INTO schema_migrations (version, applied_at)
VALUES ('2026-08-13_reconcile_open_rows', datetime('now'));

COMMIT;
