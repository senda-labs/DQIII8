---
paths:
  - "database/**"
  - "**/*.sql"
  - "bin/core/db.py"
  - "bin/core/db_security.py"
---
# Database Mutation Rules — DQIII8

## Schema Authority
`database/schema_v2.sql` is the **single source of truth**.
- Schema changes: edit `schema_v2.sql` ONLY → apply manually: `sqlite3 database/dqiii8.db < database/schema_v2.sql` (DDL is idempotent via `CREATE TABLE IF NOT EXISTS`). `python3 -m database.apply_migrations` does NOT exist.
- NEVER alter the live `dqiii8.db` schema via raw `sqlite3` (one-time data fixes excepted).
- NEVER commit `*.db`, `*.db-wal`, `*.db-shm` files — they are gitignored by design.

## Table-Specific Rules

| Table | Rule |
|---|---|
| `agent_actions` | **Audit log — append-only, DB-enforced** (`trg_agent_actions_no_delete` blocks all DELETE; `trg_agent_actions_close_once` allows exactly one UPDATE per row — filling `end_time_ms`/`duration_ms`/`success`/`error_message`/`bytes_written`/`request_id` while `end_time_ms IS NULL` — then the row is immutable, including `project`/`domain` and the cost/tier/token columns; `trg_agent_actions_no_replace` blocks `INSERT OR REPLACE`/upsert over an existing id, which otherwise bypassed every other trigger here since SQLite's REPLACE-conflict delete doesn't fire `BEFORE DELETE` under the default `recursive_triggers=0`. Fixed 2026-08-11, stress-db.md #6/#8; REPLACE bypass fixed same day, stress-reverify-and-gaps.md.) `project` and `domain` are **INSERT-only** — a writer gets exactly one chance (the initial INSERT) to set them; there is no corrective UPDATE path afterward. Column families (canonical, see `docs/audits/2026-08-13-db-attribution-rebuild.md` D4): `tokens_input`/`tokens_output` (not `input_tokens`/`output_tokens`), `estimated_cost_usd` (not `cost_eur`), `tier` TEXT (not `model_tier`). |
| `project_context` | **SSOT for "current project"** (added 2026-08-13). Append-only convention like `human_hours`: one open row per `scope` (`'global'` or a session_id), enforced by a partial unique index on `scope WHERE ended_at IS NULL`; closed via `ended_at`, never DELETE. Resolve through `bin/core/project_context.py::resolve_project()` (6-step precedence: explicit arg → `DQIII8_PROJECT` env → open row for this session → open row for `scope='global'` → cwd match under `my-projects/` → literal `'dqiii8-core'`), not by querying the table directly — it fails open (returns `None`, logs at DEBUG) rather than blocking the hot INSERT path. |
| `instincts` | **Append-only, DB-enforced** (`trg_instincts_no_delete` blocks all DELETE; `trg_instincts_immutable_identity` locks `keyword`/`pattern`/`source`/`project`/`created_at` after insert — only `times_applied`/`times_successful`/`confidence`/`last_applied` may change, via `stop.py`/`bin/agents/memory_decay.py`; `trg_instincts_no_replace` blocks the same REPLACE bypass as above. Fixed 2026-08-11, stress-db.md #7/#8; REPLACE bypass fixed same day, stress-reverify-and-gaps.md.) |
| `error_log` | Columns: `id, timestamp, session_id, agent_name, error_type, error_message, keywords, cause, resolution, resolved, resolution_ms, lesson_added, action_id, severity`. Field `summary` does NOT exist. |

`model_performance` and `session_events` were documented here previously but do not exist in
`schema_v2.sql` or the live DB — removed 2026-08-11 stress test. Real routing-feedback data
lives in `routing_feedback` instead.

`gemini_audits` was orphaned (0 rows, zero Python writers — confirmed 2026-08-11) and has
been **removed** (schema_v2.sql + live DB, user-authorized 2026-08-11): the whole
gemini-review feature (`bin/tools/gemini_review.py`, `.claude/commands/gemini-review.md`,
`.claude/skills/gemini-review/`, and its trigger in `stop.py`) was unused and deleted along
with it. `bin/tools/gemini_export.py` (manual context export for pasting into Gemini Pro)
is a separate, still-used tool and was left untouched.

## SQLite Access Patterns
- Use full path: `sqlite3 /root/dqiii8/database/dqiii8.db "…"` — no aliases in non-interactive shells.
- `error_log` lives in `dqiii8.db` ONLY — not in `dqiii8_metrics.db`.
- Always use `timeout=30` in Python `sqlite3.connect()` calls on the production DB.
- WAL mode is enabled on per-company `orchestrator_state.db` files — writes must use `asyncio.to_thread()`.

## Pre-Mutation Checklist
Before any INSERT/UPDATE/DELETE on production DB:
1. `git check-ignore -v database/dqiii8.db` → confirm it won't be staged.
2. Verify the target table exists and column names are correct.
3. For DELETE: confirm WHERE clause is present and selective.
