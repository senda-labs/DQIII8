---
paths:
  - ".claude/hooks/**"
  - ".claude/hooks/*.py"
---
# Hooks & Permissions — DQIII8

## Hook Execution Order (per tool call)
```
1. pre_tool_use.py   → PermissionAnalyzer v3 → APPROVE / DENY / ESCALATE
                      → Rules injection via rules_dispatcher.py (~200–800 tokens)
                      → Output truncation wrapper (large-output Bash commands)
2. [tool executes]
3. post_tool_use.py  → Records action to DB (agent_actions), estimates cost
```

Session lifecycle:
- `session_start.py` → injects project context, last 5 lessons, last audit state.
- `stop.py` → auto-commits uncommitted work, extracts lessons, writes session metrics.

## PermissionAnalyzer Decision Logic

| Decision | When | Consequence |
|---|---|---|
| `APPROVE` | Low-risk, within safe paths and budget | Tool proceeds |
| `DENY` | Matches CRITICAL or HIGH_RISK patterns, blocked path, budget exceeded | **Tool blocked, logged to DB. FINAL — do not retry the same call.** |
| `ESCALATE` | Ambiguous risk, needs user confirmation | Pause and ask user |

**DENY is immutable.** When the analyzer issues DENY, the rejection is logged to `agent_actions`. Do NOT attempt to bypass with `--no-verify`, `--force`, or re-ordering operations.

## Always-Blocked (CRITICAL_PATTERNS)
`rm -rf /` (exact), `> /dev/sda`, `mkfs`, `dd if=`, fork bombs.

## High-Risk (require explicit user confirmation)
`rm -rf /anything`, `DROP TABLE`, `DELETE FROM agent_actions` without WHERE, `DROP DATABASE`, `chmod 777 /`.

## Blocked Paths (DENY on write)
`.env`, `CLAUDE.md`, `database/schema.sql`, `dqiii8.db`, `.claude/settings.json`, `.git/`, `.ssh/`, `id_rsa`, `id_ed25519`.

## Rules Dispatcher
`pre_tool_use.py` calls `rules_dispatcher.py` which:
- Reads `tool_name` + `tool_input` from the hook payload.
- Maps tool → subset of rule aliases → loads only those files (~200–800 tokens).
- Injects as `additionalContext` in the hook response.
- NEVER loads all 16+ rule files at once.

## Modifying Hooks
Before changing any file in `.claude/hooks/`:
1. Identify which DB tables the hook writes to (check `agent_actions`, `session_events`).
2. Verify the change doesn't break the APPROVE/DENY/ESCALATE output contract.
3. Test with a dry run: `echo '{"tool_name":"Bash","tool_input":{"command":"ls"}}' | python3 .claude/hooks/pre_tool_use.py`.
4. A hook error must NEVER block Claude Code startup — all failures must silently degrade to `APPROVE`.
