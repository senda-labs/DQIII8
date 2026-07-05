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
- Always `sqlite3.connect(path, timeout=30)` from Python — the default (5s) and the
  hook default (10s) produce `SQLITE_BUSY` under parallel dispatch. (rule 01)
- WAL mode is set persistently; never disable it. Check `-wal` size before assuming
  a write landed.
- `database/dqiii8.db` = live state; `database/dqiii8_metrics.db` = knowledge/vector
  side; `database/dqiii8_history.db` = session_memory only. Do NOT create tables in
  the wrong file — `routing_feedback` already exists forked in two DBs (known debt).

## Dispatch / wrapper
- `dispatch.py` async mode does NOT return usable results (result file truncated by
  design bug, audit 2026-07-05) — use sync mode or tmux until fixed.
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
