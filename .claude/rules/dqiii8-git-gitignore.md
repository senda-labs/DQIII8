# DQIII8 — Git & .gitignore Safety

## NEVER add files listed in .gitignore

Before ANY `git add`, verify the file is not ignored:

```bash
git check-ignore -v <file>   # output = gitignored → DO NOT ADD
```

**Files ALWAYS gitignored in this repo (never try to add these):**
- `database/*.db` — dqiii8.db, dqiii8_metrics.db, jarvis_metrics.db
- `database/*.db-wal` / `*.db-shm` — SQLite WAL files
- `config/.env` — real config (NEVER commit credentials)
- `.claude/.credentials.json`
- `.pytest_cache/`, `__pycache__/`, `*.pyc`
- `sessions/` — ephemeral session data
- `tasks/nightly-report.md`, `tasks/results/`, `tasks/audit_pending.flag`
- `skills-registry/cache/`

## Safe git add protocol

```bash
# 1. Check status first (required by bash-safety.md)
git status

# 2. Verify file before adding
git check-ignore -v <file>   # no output = safe to add

# 3. Add by explicit path — NEVER git add -A or git add .
git add bin/core/notify.py

# 4. For renames/moves
git add -u <path>
```

## On "paths are ignored" error

If git rejects with "The following paths are ignored by one of your .gitignore files":
- **STOP** — do NOT use `git add -f` or `--force`
- Do NOT try again with the same file
- Verify it is not sensitive (DB, credentials, cache)
- If it genuinely needs version control: update `.gitignore` + request user confirmation first

## Blocked bash commands

The PermissionAnalyzer (pre_tool_use.py) blocks or escalates:
- `git add -A` / `git add .` — use explicit paths only
- `rm -rf` on critical paths — requires user confirmation
- writes to `.env`, credentials, `database/*.db`
- `git push --force` — blocked unless user explicitly requests

If a command is DENY'd by the hook, do NOT retry it. Fix the approach instead.
