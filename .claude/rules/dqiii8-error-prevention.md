# DQIII8 — Error Prevention (Recurring Patterns)

> These patterns caused 77+ unresolved errors in audit-2026-03-29.
> MANDATORY: check this before ANY git add, bash command, DB query, or file read.

## 1. NEVER `git add` gitignored paths

These are ALL gitignored — do NOT attempt to add, commit, or push them:

| Path | Why |
|------|-----|
| `tasks/` (entire dir) | Internal task state |
| `sessions/` | Ephemeral session data |
| `projects/` | Internal project state |
| `my-projects/*/` | User project contents |
| `docs/CHECKPOINT_*.md` | Premium/internal docs |
| `database/audit_reports/*.md` | Private audit reports |
| `database/*.db` | SQLite databases |
| `config/.env` | Credentials |
| `decisions/` | Internal ADR state |
| `.mcp.json` | Local MCP config |

**Before ANY `git add`:**
```bash
git check-ignore -v <file>   # if output → DO NOT ADD
```

If `git add` returns "paths are ignored" → STOP. Do NOT retry with `-f`.
These files are local-only by design. They are never committed.

## 2. NEVER query nonexistent columns

The `error_log` table schema:
```
id, timestamp, session_id, agent_name, error_type, error_message,
keywords, cause, resolution, resolved, resolution_ms, lesson_added,
action_id, severity
```

**Common mistakes:**
- ❌ `summary` → ✅ `error_message`
- ❌ `error_log` in dqiii8_metrics.db → ✅ only in dqiii8.db

## 3. NEVER `git commit` on clean working tree

Before `git commit`, check:
```bash
git status --porcelain
```
If empty → skip commit. "nothing to commit" is exit code 1 = error in logs.

## 4. NEVER check `dqiii8-director.service`

`dqiii8-director` is CLI-only (`python3 bin/director.py`). NOT a systemd service.
Only `dqiii8-bot.service` runs as systemd.

## 5. Read large files with offset/limit

Files >500 lines: ALWAYS use `offset` and `limit` parameters.
NEVER read entire file if >10K tokens. The Read tool hard-fails at this limit.

## 6. NEVER read a directory as a file

Use `ls` or `Glob` for directories. `Read` and `mcp__filesystem__read_text_file` fail on dirs.
