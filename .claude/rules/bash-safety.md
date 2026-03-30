# Bash Safety

- Loops/counters/arithmetic → Python script, never bash
- Before `git add` → run `git status` first AND `git check-ignore -v <file>` (see dqiii8-git-gitignore.md)
- Before move/delete → verify with `ls` or `test -f`
- Pipes ≤3 commands and no conditional logic → OK
- `git add -u <path>` for moves/renames, never `git add -A` / `git add .`
- `git add <file>` only for files confirmed present in `git status` AND not in .gitignore

## Blocked commands (PermissionAnalyzer will DENY)

If a Bash command is rejected by the hook, do NOT retry — fix the approach:
- `git add -A` / `git add .` → use explicit file paths
- `git add database/*.db` → blocked, DBs are gitignored
- `git add config/.env` → blocked, credentials are gitignored
- `git push --force` → blocked unless user explicitly requests
- `rm -rf` on critical paths → blocked, requires user confirmation
- `alias dqa` → aliases not available in non-interactive bash; use full command path

## Non-interactive bash

Claude Code runs bash in non-interactive mode — shell aliases are NOT available.
Always use the full command:
- WRONG: `dqa "SELECT …"` (alias not found)
- RIGHT: `sqlite3 /root/dqiii8/database/dqiii8.db "SELECT …"`
