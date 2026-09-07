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
`git push --force`/`-f`/`--force-with-lease` (any flag order, either mode, user
confirmation does not unblock it), `rm -rf /` and non-root variants, `chmod 777 /`,
`DROP TABLE`/`DROP DATABASE`, unbounded `DELETE FROM agent_actions`, writes to
`.env` / `database/*.db` / other blocked paths. Exact matchers, the full list and the
build/cache `rm` carve-out: `.claude/rules/02_hooks_and_permissions.md` (SSOT — this
is a summary, don't extend it here).

**`git add -A` and `git add .` are still NOT blocked** — no matcher, either
mode. The "Git add protocol" and "NEVER" lines above are self-discipline, not
an enforced guardrail.

## Parallel-agent sessions on the shared tree (Rango 3, 2026-08-19 red-team audit)
Worktree isolation only auto-applies to 3 agent types (`subagent_start.py`) — most
parallel agents write git state directly on the main tree, with no lock. Confirmed
live: `git worktree list` showed only the main tree while sibling agents were
active. Decision (explicit, not a code fix): keep this as-is — mandatory worktree
for every agent type was rejected as too costly to current work velocity. The
mitigation is operational discipline at session-close time, not a mechanism:
- Before closing/handing off a session that ran parallel agents, `git status`
  first — don't assume the tree is clean because your own agent's task finished.
- Don't start a new write (`git add`/commit/`stop.py`'s auto-commit path) while a
  sibling agent might still be mid-write on the same tree; check for other live
  sessions first if unsure.
- If a collision is suspected (unexpected staged files, a commit that doesn't
  match what you just did), stop and inspect before committing over it — never
  force through with `git add -A`/`-f` to "just get past it".
