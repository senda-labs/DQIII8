# /mobilize — Multi-Agent Coordination Protocol

## Trigger Conditions
- User invokes `/mobilize`
- User says "coordinate" + describes 3+ distinct domains
- Task touches 3+ unrelated domains simultaneously

## Protocol

### Step 1 — Decompose (Orchestrator, Plan Mode)
1. Enter plan mode immediately.
2. Break the goal into sub-tasks, one per domain/concern.
3. Write decomposition to `tasks/todo.md` under **Queued**.
4. Write agent assignments to `tasks/status.md` (format below).
5. Maximum 5 parallel agents.

### Step 2 — Spawn Agents
For each sub-task:
- Spawn a Task agent with the appropriate agent type (see CLAUDE.md Delegation table).
- Pass only the minimum context needed for that sub-task.
- Every agent gets an isolated worktree (`isolation: worktree`).
- Each agent writes its result to `tasks/results/{agent_name}-{YYYY-MM-DD}.md`.
- Agents NEVER write to `tasks/todo.md`.

### Step 3 — Monitor
- Poll `tasks/results/` until all expected result files appear.
- Update `tasks/status.md` as agents complete.
- If an agent fails or times out, note in `tasks/status.md` and re-spawn once.

### Step 4 — Aggregate
- Read all result files from `tasks/results/`.
- Synthesize into a final summary for the user.
- Move completed tasks in `tasks/todo.md` from **Queued/In Progress** → **Done**.
- Clean up `tasks/status.md`.

---

## tasks/status.md Format

```
# Mobilize Status — {goal summary}
Started: {timestamp}

| Agent | Sub-task | Status | Result file |
|-------|----------|--------|-------------|
| python-specialist | Refactor X | done | tasks/results/python-specialist-2026-03-11.md |
| code-reviewer | Review PR | running | — |
```

---

## Constraints
- Max 5 parallel agents.
- Each agent: isolated worktree at `/tmp/jarvis-wt/{agent_id}`.
- Orchestrator does NOT share its context window with subagents.
- Destructive actions always require user confirmation before spawning agents.
- If decomposition is unclear, ask the user ONE clarifying question before proceeding.
