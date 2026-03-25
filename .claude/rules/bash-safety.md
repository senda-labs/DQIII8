# Bash Safety

- Loops/counters/arithmetic → Python script, never bash
- Before `git add` → run `git status` first
- Before move/delete → verify with `ls` or `test -f`
- Pipes ≤3 commands and no conditional logic → OK
- `git add -u <path>` for moves/renames, never `git add -A`
- `git add <file>` only for files confirmed present in `git status`
