---
name: checkpoint
description: Save and verify session state using git commits and a checkpoints log. Use before risky multi-file changes or after completing a significant implementation block.
command: /checkpoint
allowed-tools: [Bash, Read]
user-invocable: true
auto-invoke:
  - when: "Significant code changes completed (3+ files modified and tests pass)"
    action: "Suggest /checkpoint create after implementation block"
---

# /checkpoint — Save and Verify Session State

Save or verify a named checkpoint using git + `.claude/checkpoints.log`.

## Usage

```
/checkpoint create [name]    — Save current state
/checkpoint verify [name]    — Compare current state to checkpoint
/checkpoint list             — Show recent checkpoints
```

## Create Checkpoint

When `create [name]` is called:

1. Run `/quality-gate` quick check (black + pytest -x -q)
2. Create a git commit with the checkpoint name:
   ```bash
   git add -p   # stage only intended changes
   git commit -m "checkpoint: [name]"
   ```
3. Append to `.claude/checkpoints.log`:
   ```bash
   echo "$(date +%Y-%m-%d-%H:%M) | [name] | $(git rev-parse --short HEAD)" >> .claude/checkpoints.log
   ```
4. Report: `CHECKPOINT CREATED: [name] @ [hash]`

## Verify Checkpoint

When `verify [name]` is called:

1. Read the checkpoint hash from `.claude/checkpoints.log`
2. Compare current state:
   ```bash
   git diff [hash]..HEAD --stat
   git diff [hash]..HEAD -- '*.py' | head -60
   ```
3. Report:
   ```
   CHECKPOINT COMPARISON: [name]
   ==============================
   Commits since: N
   Files changed: X added / Y modified / Z deleted
   Build: PASS / FAIL
   Tests: +N passed / -N failed
   ```

## List Checkpoints

```bash
cat .claude/checkpoints.log | tail -20
```

## Typical Workflow

```
/checkpoint create "before-p2a"
  → implement 5 skills + 3 commands
/checkpoint verify "before-p2a"
  → confirm only expected files changed
/checkpoint create "p2a-complete"
```

## Arguments

- `create [name]`: name must be `[a-z0-9-_]+`, max 40 chars
- `verify [name]`: name from log, exact match
- `list`: no args — shows last 20 entries

## Notes

- Checkpoints are git commits — they survive context compaction
- Use before risky multi-file changes (P2, P3 batches)
- Combine with `strategic-compact`: compact AFTER creating checkpoint
