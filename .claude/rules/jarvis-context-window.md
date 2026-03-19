# DQIII8 — Context Window Management

Context limit: **1 000 000 tokens** (Claude Sonnet 4.6, plan Max).
Auto-compact triggers at 50% (~500 K tokens) via `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`.

| Zone   | % used | Tokens used  | Action |
|--------|--------|--------------|--------|
| Green  | <40%   | <400 K       | Work normally. |
| Yellow | 40-60% | 400 K–600 K  | Stop loading skills. Unload unused ones. |
| Orange | 60-75% | 600 K–750 K  | Alert in terminal. Finish current task, then compact. |
| Red    | >75%   | >750 K       | Trigger /clear-context immediately. |

- After /clear-context: stop.py saves state → 5-line summary → /clear → session_start.py reloads essentials.
- PostCompact hook reinjests: modelo activo, proyecto, últimas 3 lecciones, score de auditoría.
- Every worktree starts with clean context. Orchestrator does NOT share its context with subagents.
