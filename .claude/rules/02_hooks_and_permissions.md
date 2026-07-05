---
paths:
  - ".claude/hooks/**"
  - ".claude/hooks/*.py"
---
# Hooks & Permissions — DQIII8

**Order**: `pre_tool_use.py` (PermissionAnalyzer → APPROVE/DENY/ESCALATE + rules_dispatcher.py injection, ~200–800 tokens) → tool runs → `post_tool_use.py` (logs to `agent_actions`, estimates cost).
**Session**: `session_start.py` injects context+lessons; `stop.py` auto-commits + writes metrics.

| Decision | Trigger | Result |
|---|---|---|
| APPROVE | low-risk, safe path, under budget | proceeds |
| DENY | CRITICAL/HIGH_RISK pattern, blocked path, budget exceeded | **blocked, logged, final — never retry or bypass (no `--no-verify`/`--force`/reordering)** |
| ESCALATE | ambiguous risk | pauses for user |

**Always-blocked commands**: `rm -rf /` (exact), `> /dev/sda`, `mkfs`, `dd if=`, fork bombs.
**High-risk (needs user confirmation)**: `rm -rf /anything`, `DROP TABLE`, `DELETE ... agent_actions` w/o WHERE, `DROP DATABASE`, `chmod 777 /`.

**Blocked paths — DENY on write, absolute, no carve-outs, source of truth = `BLOCKED_PATHS` in `permission_analyzer.py`:**
`CLAUDE.md`, `.env`, `secrets`, `dqiii8.db`, `.claude/settings.json`, `schema.sql`, `.git/`, `id_rsa`, `id_ed25519`, `.ssh/`, `context/proposito.md`.
No exception for "user asked for it" — the code has none. A human edits these directly, outside any agent session. (Other docs, e.g. `dqiii8-ops.md`, must not restate this list — link here instead, to avoid drift.)

**Rules dispatcher**: maps tool+input → 1-3 rule aliases from `.claude/rules_db/` (~200-800 tokens); never loads all files.

**Before editing anything in `.claude/hooks/`**: check which DB tables it writes (`agent_actions`/`session_events`) → confirm APPROVE/DENY/ESCALATE contract unchanged → dry-run (`echo '{"tool_name":"Bash","tool_input":{"command":"ls"}}' | python3 .claude/hooks/pre_tool_use.py`) → hook errors must silently degrade to APPROVE, never block startup.
