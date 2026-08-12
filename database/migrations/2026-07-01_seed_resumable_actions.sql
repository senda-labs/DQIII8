-- Seed idempotente de resumable_actions, generado desde
-- my-projects/jarvis-control3/config/actions.yaml (fuente única — ver architecture/08-allowlist-and-secrets.md).
-- Regenerar este fichero manualmente si actions.yaml cambia (deuda: automatizar en CI, ver INDEX.md).

INSERT INTO resumable_actions (action_id, kind, entrypoint, arg_schema, requires_checkpoint, enabled)
VALUES
  ('cobrowsing_batch', 'standalone_script',
   'my-projects/intl-reports/scripts/cobrowsing_batch.py',
   '{"type":"object","additionalProperties":false,"properties":{"company_slug":{"type":"string"}},"required":["company_slug"]}',
   1, 1),
  ('cdp_bet365_full', 'standalone_script',
   'my-projects/football-value/scripts/cdp_bet365_full.py',
   '{"type":"object","additionalProperties":false,"properties":{"match_id":{"type":"string"}},"required":["match_id"]}',
   1, 1)
ON CONFLICT(action_id) DO NOTHING;
