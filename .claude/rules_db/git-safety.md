# Git & Bash Safety

## Bash rules
- Loops/counters/arithmetic → Python script, never bash
- Before move/delete → verify with `ls` or `test -f`
- Pipes ≤3 commands, no conditional logic → OK
- Non-interactive mode: aliases NOT available — use full paths
  - WRONG: `dqa "SELECT …"` | RIGHT: `sqlite3 /root/dqiii8/database/dqiii8.db "…"`

## Git add protocol (MANDATORY)
```bash
git status                        # 1. check first
git check-ignore -v <file>        # 2. no output = safe to add
git add bin/core/notify.py        # 3. explicit path only
git add -u <path>                 # 4. for renames/moves
```
- NEVER `git add -A` / `git add .` — use explicit paths
- NEVER `git add -f` on gitignored paths — STOP and fix approach
- NEVER commit on clean working tree (check `git status --porcelain`)

## Commit message format
`<type>: <description>` — types: feat, fix, refactor, docs, test, chore, perf, ci.
DQIII8 commits DO carry the attribution trailer (unlike the ECC default):
`Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`

## Always gitignored — NEVER try to add
- `database/*.db` / `*.db-wal` / `*.db-shm`
- `config/.env` — credentials
- `.claude/.credentials.json`
- `__pycache__/`, `*.pyc`, `.pytest_cache/`
- `sessions/`, `tasks/results/`, `tasks/audit_pending.flag`
- `my-projects/*/` — private project contents
- `skills-registry/cache/`

## PermissionAnalyzer will DENY
`rm -rf /` (and non-root variants), `chmod 777 /`, `DROP TABLE`/`DROP DATABASE`,
`DELETE FROM agent_actions` without `WHERE`, writes to `.env` / `database/*.db` /
other `BLOCKED_PATHS` (see `.claude/rules/02_hooks_and_permissions.md`).
Exception: a recursive-force `rm` whose targets are *all* build/cache artifacts
(`node_modules`, `dist`, `__pycache__`, …) is approved — see that file's
`ALLOWED_DELETIONS` carve-out for the exact rule.

**`git push --force` IS blocked** (2026-08-18): a `HIGH_RISK_PATTERNS` entry in
`permission_analyzer.py` DENIES `git push` with `--force`/`-f`/`--force-with-lease`
in any flag order, in either mode — same verdict as `rm -rf`/`DROP`.

**`git add -A` and `git add .` are still NOT blocked** — no matcher, either
mode. The "Git add protocol" and "NEVER" lines above are self-discipline, not
an enforced guardrail.
