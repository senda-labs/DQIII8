# DQIII8 — Architecture Kernel

Autonomous AI orchestration engine (VPS, SSH-only).
UI: Telegram @YourBotName | CLI: `dq cc` / `dq loop` / `dq status`

## Routing Tiers (Cost-First — STRICT)
Anthropic-only vigente (directiva usuario 2026-08-18): Sonnet (default) → Opus (plan-review/
revisión adversarial final únicamente). Cadena multi-tier gratuita (C→B→B+→B++) DORMANTE, no
eliminada — ver `.claude/rules_db/archive/multi-tier-dormant-2026-08.md`.
Full table + decision algorithm → `.claude/rules/03_tiering_and_routing.md`

## System Map
- DQ Pipeline (7 steps): Classify → Retrieve → Gate → Amplify → Route → Execute → Memory
- DB: `database/dqiii8.db` (schema_v2.sql — source of truth, now also holds `session_memory`; sibling: `dqiii8_knowledge.db` knowledge/vector. `dqiii8_history.db` and `dqiii8_metrics.db.old` are frozen post-migration artifacts, 2026-08-14)
- Writing to `agent_actions`: use `bin/core/action_log.py`'s shared helpers (`resolve_project_safe()`, `generate_request_id()`) — see `docs/audits/2026-08-13-db-attribution-rebuild.md`
- Hooks (14): `.claude/hooks/` | Skills (22): `.claude/skills/` | Agents (17): `.claude/agents/`
- Contextual rules (17): `.claude/rules_db/` — not read directly; injected 1-3 files at a time per tool call by `rules_dispatcher.py` (see `.claude/rules/02_hooks_and_permissions.md`).
- Entry: `bin/core/openrouter_wrapper.py` | Director: `bin/director.py`
- Dispatch (CC↔dqiii8): `bin/core/dispatch.py` — thin subprocess shim; sync + async (async fixed 2026-07-05 via detached worker + atomic JSON envelope — see `docs/audits/2026-07-fable5-remediation-report.md`)

> **`docs/audits/` durability does NOT come from git.** That path is gitignored on
> purpose (F-26 leak, 2026-08-17) even though rules and skills cite it as a source of
> truth. Its only copies live off-VPS, via two independent channels: `bin/tools/backup_audit_docs.sh`
> (mutual Netcup↔Hostinger rsync, dated snapshots, no `--delete` mirror) and
> `bin/tools/telegram_audit_backup.py` (per-file upload to a single allowlisted Telegram chat).
> Both read their targets/credentials from env vars only. `database/audit_reports/*.md`
> *is* tracked in git (narrow `.gitignore` negation + `audit-docs-*` gitleaks rules).
> Deleting a file under `docs/audits/` is effectively irreversible once both backups roll.

> **Not DQIII8-specific**: `.claude/architecture/` holds a generic reference book on Claude Code's own internals (agent loop, tool execution, etc.), unrelated to DQIII8's architecture. Don't confuse it with DQIII8 docs when orienting.

## Rule Engine

| Domain | Read this first |
|---|---|
| Any action | `.claude/rules/00_core_behavior.md` (always loaded — zero-complacency, scope, cost-first) |
| DB schema / SQL / sqlite3 | `.claude/rules/01_database_mutations.md` |
| Hooks or PermissionAnalyzer | `.claude/rules/02_hooks_and_permissions.md` |
| Tiering / routing / agent changes | `.claude/rules/03_tiering_and_routing.md` |
| Delegación a agentes / qué nombres existen | `.claude/rules_db/common/agents.md` § Two runtimes, two SSOTs |
| Git / Bash safety | `.claude/rules_db/git-safety.md` |
| Error prevention (recurring) | `.claude/rules_db/dqiii8-error-prevention.md` |
| intl-reports pipeline | `my-projects/intl-reports/RULE` (reglas absolutas + pipeline) |

## Inviolable Rules
- NEVER write to `.env` or `CLAUDE.md` from generated code. `database/schema_v2.sql` is the schema SSOT — additive changes only, via reviewed migrations; destructive schema changes → flag, never execute. (`database/schema.sql` no longer exists.)
- NEVER hardcode API keys — all keys via `os.environ.get("VAR")` only.
- NEVER commit `*.db` files — gitignored. Use `database/schema_v2.sql` for fresh installs.
- `ANTHROPIC_API_KEY` must be `""` in subprocess env when using Claude Code OAuth.
- Plans touching ≥3 modules OR with ambiguous scope → enter plan mode first, then
  run `/panel-review <plan-file>` before implementation (see `.claude/skills/panel-review/`).
- Destructive / irreversible actions (rm -rf, DROP, force-push) → STOP, notify, wait.
