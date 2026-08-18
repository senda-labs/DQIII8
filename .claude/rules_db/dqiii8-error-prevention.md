# Error Prevention — Recurring Failure Modes (DQIII8)

Referenced by `CLAUDE.md` rule table and `rules_dispatcher.py` alias `prevention`
(injected on Read, git, sqlite3, systemctl commands). Created 2026-07-05 (Fable 5
audit) — the alias pointed at a missing file, so these rules were silently never
injected. Every rule below traces to a real, documented recurring error.

## Environment / auth
- `ANTHROPIC_API_KEY` must be `""` in subprocess env when using Claude Code OAuth.
  Symptom of violation: "Credit balance too low". (DYNAMIC.md, universal rule)
- Non-interactive shells have NO aliases — always full paths:
  `sqlite3 /root/dqiii8/database/dqiii8.db "…"`, never `dqa "…"`. (git-safety.md)

## SQLite
- `sqlite3.connect(path, timeout=30)` for batch/background/one-off scripts (migrations,
  backfills, `bin/tools/*`) — the driver default (5s) produces `SQLITE_BUSY` under
  parallel dispatch. **Hooks and other hot-path callers deliberately use shorter,
  tiered timeouts (0.5–10s)** to fail open fast under lock contention instead of
  blocking a tool call — this is intentional design (Opus review P3-11, 2026-08-13:
  ~96 call sites audited, all short timeouts pair with a graceful-degradation
  try/except), not an oversight to "fix" to 30. See `01_database_mutations.md`.
- WAL mode is set persistently; never disable it. Check `-wal` size before assuming
  a write landed.
- `database/dqiii8.db` = live state, now also `session_memory` (migrated 2026-08-14);
  `database/dqiii8_knowledge.db` = knowledge/vector side. `dqiii8_history.db` and
  `dqiii8_metrics.db.old` are frozen post-migration artifacts, not written anymore.
  Do NOT create tables in the wrong file — `routing_feedback` already exists forked
  in two DBs (known debt, predates this migration).

## Dispatch / wrapper
- `dispatch.py` async mode FIXED 2026-07-05 (detached worker + atomic `os.replace()`
  JSON envelope) — `tests/test_dispatch_async.py` covers it. Sync and async both usable.
- Provider fallback prints partial output from a failed stream BEFORE the fallback
  provider's full answer — never parse dispatch stdout as a clean single response
  for critical flows; prefer checking `agent_actions` for the authoritative record.
- A dispatch `timeout` status does NOT mean the wrapper failed — its outer 120s
  default is shorter than the wrapper's own per-provider timeouts; check
  `agent_actions` before retrying (double-execution risk).

## Session hygiene
- After compact/resume: read `PROJECT.md` + phase/status before ANY action
  (feedback_intl_post_compact). Never re-derive state from memory alone.
- Something breaks mid-plan → STOP, re-plan, ask if uncertain. Never "keep going"
  past a failure (dqiii8-ops.md).
