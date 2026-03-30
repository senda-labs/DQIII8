# Development Workflow & Hooks

## Feature implementation (mandatory order)
0. **Research first**: `gh search code`, PyPI/npm registries, prior art — before writing new code
1. **Plan**: use planner agent; generate PRD/architecture/task_list before coding
2. **TDD**: write test first (RED) → implement (GREEN) → refactor; 80%+ coverage
3. **Review**: code-reviewer agent immediately after writing; fix CRITICAL+HIGH
4. **Commit**: conventional commits format (see git-workflow.md)

## Hooks reference
- **PreToolUse**: validate/deny before execution
- **PostToolUse**: auto-format, metrics, checks (Black runs here for .py)
- **Stop**: session close, auto-commit, lessons
- Never use `dangerously-skip-permissions`; configure `allowedTools` instead

## Design patterns
- **Repository pattern**: abstract data access behind findAll/findById/create/update/delete
- **API envelope**: `{success, data, error, metadata}` on every response
- **Skeleton first**: search for proven project templates before building from scratch

## TodoWrite
Use for multi-step tasks: reveals out-of-order steps, missing items, wrong granularity
