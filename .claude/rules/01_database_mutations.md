# Database Mutation Rules — DQIII8

## Schema Authority
`database/schema_v2.sql` is the **single source of truth**.
**Precedencia (una sola regla): un agente edita `schema_v2.sql` y para ahí.** Aplicar schema a
una DB es trabajo humano — `dqiii8.db` es blocked-path (`02_hooks_and_permissions.md`) y el
cambio es destructivo (`00_core_behavior.md` → STOP y avisar). Las viñetas de abajo separan
**instalación nueva** (lo que corre el humano) de **DB viva** (lo que no corre nadie).

- Schema changes: un agente edita `schema_v2.sql` ONLY. En una **instalación nueva / DB vacía**, el humano lo aplica a mano con `sqlite3 database/dqiii8.db < database/schema_v2.sql` (DDL idempotente vía `CREATE TABLE IF NOT EXISTS`). `python3 -m database.apply_migrations` does NOT exist.
- **Views are `CREATE VIEW IF NOT EXISTS`, not `CREATE OR REPLACE`**: reapplying `schema_v2.sql` to an *existing* DB silently no-ops on any view that already exists — editing a view's SQL in `schema_v2.sql` alone does NOT update a live DB. A changed view definition needs an explicit `database/migrations/*.up.sql` doing `DROP VIEW IF EXISTS <name>; CREATE VIEW <name> AS ...`, applied by hand, in addition to updating `schema_v2.sql` for fresh installs.
- Contra la **DB viva**: NEVER alter its schema via raw `sqlite3` — ni un agente, ni "solo esta vez". Un cambio de vista/tabla ya desplegado necesita el `database/migrations/*.up.sql` descrito arriba, escrito por el agente y **aplicado por el humano**. (Los one-time *data* fixes — INSERT/UPDATE de filas, sin DDL — sí caben, con el checklist de abajo.)
- NEVER commit `*.db`, `*.db-wal`, `*.db-shm` files — they are gitignored by design.

## Table-Specific Rules

| Table | Rule |
|---|---|
| `agent_actions` | **Audit log — append-only, DB-enforced** (`trg_agent_actions_no_delete` blocks all DELETE; `trg_agent_actions_close_once` allows exactly one UPDATE per row — filling `end_time_ms`/`duration_ms`/`success`/`error_message`/`bytes_written` while `end_time_ms IS NULL` — then the row is immutable, including `project`/`domain`/`request_id` and the cost/tier/token columns; `trg_agent_actions_no_replace` blocks `INSERT OR REPLACE`/upsert over an existing id, which otherwise bypassed every other trigger here since SQLite's REPLACE-conflict delete doesn't fire `BEFORE DELETE` under the default `recursive_triggers=0`.) `project`, `domain`, and `request_id` are **INSERT-only** — a writer gets exactly one chance (the initial INSERT) to set them, including `request_id` (`trg_agent_actions_close_once`'s WHEN clause aborts if the close-out UPDATE changes it — set it correctly on INSERT, there is no corrective UPDATE path afterward). Column families (canonical — this list, plus `schema_v2.sql` itself; do not cite gitignored audit docs as the source): `tokens_input`/`tokens_output` (not `input_tokens`/`output_tokens`), `estimated_cost_usd` (not `cost_eur`), `tier` TEXT (not `model_tier`). |
| `project_context` | **SSOT for "current project"**. Append-only convention like `human_hours`: one open row per `scope` (`'global'` or a session_id), enforced by a partial unique index on `scope WHERE ended_at IS NULL`; closed via `ended_at`, never DELETE. Resolve through `bin/core/project_context.py::resolve_project()` (5-step precedence: explicit arg → open row for this session → open row for `scope='global'` → cwd match under `my-projects/` → literal `'dqiii8-core'`; a `DQIII8_PROJECT` env-var step doesn't work — each hook is a fresh subprocess, so nothing one hook writes to `os.environ` is ever visible to another), not by querying the table directly — it fails open (returns `None`, logs at DEBUG) rather than blocking the hot INSERT path. |
| `instincts` | **Append-only, DB-enforced** (`trg_instincts_no_delete` blocks all DELETE; `trg_instincts_immutable_identity` locks `keyword`/`pattern`/`source`/`project`/`created_at` after insert — only `times_applied`/`times_successful`/`confidence`/`last_applied` may change, via `stop.py`/`bin/agents/memory_decay.py`; `trg_instincts_no_replace` blocks the same REPLACE bypass as above.) |
| `error_log` | Columns: `id, timestamp, session_id, agent_name, error_type, error_message, keywords, cause, resolution, resolved, resolution_ms, lesson_added, action_id, severity`. Field `summary` does NOT exist. |

Tables that do **not** exist — don't write to them, don't "restore" them:
`model_performance`, `session_events` (routing feedback lives in `routing_feedback`),
`gemini_audits` (removed with the whole gemini-review feature).

## SQLite Access Patterns
- Use full path: `sqlite3 /root/dqiii8/database/dqiii8.db "…"` — no aliases in non-interactive shells.
- `error_log` in `dqiii8.db` (1698 rows, live, growing — `severity` column present) is the SSOT
  for writes; every active writer (`stop.py`, `post_tool_use*.py`, `bin/tools/*`) targets it.
  A second, **stale** copy exists in `dqiii8_knowledge.db` (856 rows, no `severity` column,
  frozen at the 2026-08-14 consolidation — see `database/backups/pre-consolidation-20260814T134859Z/`)
  and nothing writes to it anymore. Confirmed bug: `bin/ui/dashboard.py` reads `error_log` from
  `dqiii8_knowledge.db`, so its error view is stale/incomplete by ~842 rows and has been since
  the consolidation — not yet fixed, flag before trusting dashboard error counts.
- Use `timeout=30` for batch/background/one-off scripts that mutate the production DB (migrations, backfills, `bin/tools/*`). **Hot-path callers (hooks) deliberately use shorter tiered timeouts (0.5–10s)** to fail open fast under lock contention instead of blocking a tool call; each pairs with a graceful-degradation `try/except`. Don't "fix" a short hook timeout to 30 without checking it isn't this pattern.
- WAL mode is enabled on per-company `orchestrator_state.db` files — writes must use `asyncio.to_thread()`.

## Pre-Mutation Checklist
Before any INSERT/UPDATE/DELETE on production DB:
1. `git check-ignore -v database/dqiii8.db` → confirm it won't be staged.
2. Verify the target table exists and column names are correct.
3. For DELETE: confirm WHERE clause is present and selective.
