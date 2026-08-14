# Legacy Schema Files

These files are historical references only. **Do not use for fresh installs or migrations.**

| File | Era | Notes |
|---|---|---|
| `schema.sql` | Pre-v2 | Original 19KB schema, ~50 tables, no metrics/audit infrastructure |
| `schema_temporal.sql` | Pre-v2 | Temporal table experiments, never promoted to production |

## Canonical source

`database/schema_v2.sql` — 75KB, 58 tables + 29 views, includes metrics, audit, agent_actions, token_usage, error_log, vault_memory. Apply via `sqlite3 database/dqiii8.db < database/schema_v2.sql` (see `.claude/rules/01_database_mutations.md` — `bin/tools/db_init.py` does not exist).
