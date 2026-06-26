# DQIII8 — Architecture Kernel

Autonomous AI orchestration engine (VPS, SSH-only).
UI: Telegram @YourBotName | CLI: `dq cc` / `dq loop` / `dq status`

## Routing Tiers (Cost-First — STRICT)
C (Ollama/local $0) → B (Groq $0) → B+ (NIM $0, 40RPM, 1M ctx) → B++ (GitHub $0) → A (Sonnet ~$0.03) → S (Opus ~$0.20)
Start cheap. Escalate only on explicit task-type match or tier failure.
Full table + decision algorithm → `.claude/rules/03_tiering_and_routing.md`

## System Map
- DQ Pipeline (7 steps): Classify → Retrieve → Gate → Amplify → Route → Execute → Memory
- DB: `database/dqiii8.db` (schema_v2.sql — source of truth)
- Hooks (14): `.claude/hooks/` | Skills (21): `.claude/skills/` | Agents (17): `.claude/agents/`
- Entry: `bin/core/openrouter_wrapper.py` | Director: `bin/director.py`
- Dispatch (CC↔dqiii8): `bin/core/dispatch.py`

## Rule Engine

| Domain | Read this first |
|---|---|
| Any action | `.claude/rules/00_core_behavior.md` (always loaded — zero-complacency, scope, cost-first) |
| DB schema / SQL / sqlite3 | `.claude/rules/01_database_mutations.md` |
| Hooks or PermissionAnalyzer | `.claude/rules/02_hooks_and_permissions.md` |
| Tiering / routing / agent changes | `.claude/rules/03_tiering_and_routing.md` |
| Git / Bash safety | `.claude/rules_db/git-safety.md` |
| Error prevention (recurring) | `.claude/rules_db/dqiii8-error-prevention.md` |
| intl-reports pipeline | `my-projects/intl-reports/RULE` (reglas absolutas + pipeline) |

## Inviolable Rules
- NEVER write to `.env`, `CLAUDE.md`, `database/schema.sql` from generated code.
- NEVER hardcode API keys — all keys via `os.environ.get("VAR")` only.
- NEVER commit `*.db` files — gitignored. Use `database/schema_v2.sql` for fresh installs.
- `ANTHROPIC_API_KEY` must be `""` in subprocess env when using Claude Code OAuth.
- Plans touching ≥3 modules OR with ambiguous scope → enter plan mode first.
- Destructive / irreversible actions (rm -rf, DROP, force-push) → STOP, notify, wait.
