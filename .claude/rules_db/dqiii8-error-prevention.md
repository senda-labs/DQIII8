# Error Prevention — Recurring Failure Modes (DQIII8)

## SQLite
- Connection timeouts (batch 30s vs. hooks' shorter tiered ones): SSOT
  `01_database_mutations.md` §SQLite Access Patterns. Symptom of getting it wrong:
  `SQLITE_BUSY` under parallel dispatch.
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
- After compact/resume: re-read the project's own state file — `my-projects/<proyecto>/PROJECT.md`
  — plus whatever status command that project documents, before ANY action. Never re-derive state
  from memory alone.
