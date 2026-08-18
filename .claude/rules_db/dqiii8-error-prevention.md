# Error Prevention — Recurring Failure Modes (DQIII8)

## Environment / auth
- `ANTHROPIC_API_KEY` must be `""` in subprocess env when using Claude Code OAuth.
  Symptom of violation: "Credit balance too low". (DYNAMIC.md, universal rule)

## SQLite
- `sqlite3.connect(path, timeout=30)` for batch/background scripts — the driver default (5s)
  produces `SQLITE_BUSY` under parallel dispatch. Hooks intentionally use shorter timeouts:
  `01_database_mutations.md` §SQLite Access Patterns.
- WAL mode is set persistently; never disable it. Check `-wal` size before assuming
  a write landed.
- DB inventory (live / knowledge / frozen) → `CLAUDE.md` §System Map. Do NOT create tables
  in the wrong file — `routing_feedback` already exists forked in two DBs (known debt).

## Dispatch / wrapper
- Never parse dispatch stdout as a clean single response: provider fallback prints the
  failed stream's partial output before the fallback's answer. `agent_actions` is the
  authoritative record.
- A dispatch `timeout` status does NOT mean the wrapper failed (outer 120s default <
  per-provider timeouts). Check `agent_actions` before retrying — double-execution risk.

## Session hygiene
- After compact/resume: read `PROJECT.md` + phase/status before ANY action
  (feedback_intl_post_compact). Never re-derive state from memory alone.
