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
- Schema changes: edit `schema_v2.sql` ONLY → run `python3 -m database.apply_migrations`.
- NEVER alter the live `dqiii8.db` schema via raw `sqlite3` (one-time data fixes excepted).
- NEVER commit `*.db`, `*.db-wal`, `*.db-shm` files — they are gitignored by design.

## Table-Specific Rules

| Table | Rule |
|---|---|
| `agent_actions` | **Audit log — append only.** `DELETE` requires a `WHERE` clause. NEVER mass-delete. |
| `instincts` | **Append-only.** Managed by `bin/tools/auto_learner.py`. Confidence decay handles stale rows. |
| `model_performance` | Written by `openrouter_wrapper.py` after each LLM call. Do NOT manually edit scores — they drive routing. |
| `error_log` | Columns: `id, timestamp, session_id, agent_name, error_type, error_message, keywords, cause, resolution, resolved, resolution_ms, lesson_added, action_id, severity`. Field `summary` does NOT exist. |
| `session_events` | Read-only from application code. Budget checks read from here. |

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
