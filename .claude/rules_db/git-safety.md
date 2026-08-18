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
(merged here 2026-08-17 from the deleted orphan `common/git-workflow.md`, whose
copy was stale at "Sonnet 4.6" — this line is the only DQIII8-specific fact it held.)

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

**`git add -A`, `git add .`, and `git push --force` are NOT technically blocked** —
`permission_analyzer.py` has no rule for them. The "Git add protocol" and "NEVER"
lines above are agent self-discipline, not an enforced guardrail; nothing in the
code stops a non-compliant run from executing them.
