# Legacy Schema Files

These files are historical references only. **Do not use for fresh installs or migrations.**

| File | Era | Notes |
|---|---|---|
| `schema.sql` | Pre-v2 | Original 19KB schema, ~50 tables, no metrics/audit infrastructure |
| `schema_temporal.sql` | Pre-v2 | Temporal table experiments, never promoted to production |

## Canonical source

`database/schema_v2.sql` — 47KB, 79 tables, includes metrics, audit, agent_actions, token_usage, error_log, vault_memory. Apply via `bin/tools/db_init.py`.
