---
name: strategic-compact
description: Suggests manual context compaction at logical task boundaries to avoid mid-task context loss. Complements jarvis-context-window.md thresholds with boundary-aware compaction timing.
origin: ECC/affaan-m (adaptado para JARVIS — complementa jarvis-context-window.md)
status: APROBADA
---

# Strategic Compact Skill

## Problem

Auto-compaction triggers at arbitrary points — often mid-task, losing active context.
JARVIS's Red threshold (>75%) triggers `/clear-context` but doesn't account for logical boundaries.

## When to Compact Manually

Compact at these boundaries, NOT mid-phase:

| Boundary | When to compact |
|----------|----------------|
| After planning | Plan written to `tasks/todo.md`, before coding starts |
| After debugging | Root cause found and fixed, before new feature work |
| After a complete commit | Session milestone reached |
| Before major context shift | Switching from jarvis-core to content-automation |
| After research phase | Facts indexed in ctx sandbox, before implementation |

## When NOT to Compact

- Mid-implementation (active files in context)
- While debugging a traceback (stack context needed)
- During a multi-step `/mobilize` sequence
- When a subagent is running

## How to Compact Safely

**Before compacting:**
1. Save active state to file (tasks/todo.md or tasks/results/)
2. Write key variables, paths, and next step explicitly
3. If mid-session: `stop.py` saves session state automatically

**Compact command:**
```
/compact [summary of what to preserve]
```

Example:
```
/compact Implementing P2a ECC skills. Next: update INDEX.md. Files created: 5 skills in skills-registry/custom/. Still need: 3 commands in .claude/commands/.
```

**After compacting:**
- `session_start.py` reloads essentials (project state, audit score, vault)
- `precompact_state.json` available at `tasks/precompact_state.json`
- Resume from the summary you wrote before compacting

## JARVIS Context Thresholds (from jarvis-context-window.md)

| Color | % Used | Action |
|-------|--------|--------|
| Green | <40% | Work normally |
| Yellow | 40-60% | Stop loading skills |
| Orange | 60-75% | Alert in terminal |
| Red | >75% | Trigger /clear-context |

**Strategic compact zone: 50-65%** — compact at next logical boundary before hitting Orange.

`CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50` (active in settings.json) lowers auto-compact to 50%.
Use this skill to compact intentionally before that threshold.

## Best Practices

1. **Compact after planning** — Plan in TodoWrite, then compact to start fresh
2. **Compact after debugging** — Clear error context before new work
3. **Write state before compacting** — Anything not in a file is lost
4. **Use the summary message** — It becomes the opening context after compact
5. **Never compact mid-refactor** — Keep modified files in context until all changes are verified

## Related

- `jarvis-context-window.md` — threshold rules
- `tasks/precompact_state.json` — state saved by precompact.py hook
- `/checkpoint` — git-based state save (complementary, not redundant)
