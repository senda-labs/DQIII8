# JARVIS — Context Window Management

- Green (<40%): work normally.
- Yellow (40-60%): stop loading skills. Unload unused ones.
- Orange (60-75%): alert in terminal.
- Red (>75%): trigger /clear-context immediately.
- After /clear-context: stop.py saves state → 5-line summary → /clear → session_start.py reloads essentials.
- Every worktree starts with clean context. Orchestrator does NOT share its context with subagents.
