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
- DB: `database/dqiii8.db` (schema_v2.sql — source of truth, now also holds `session_memory`; sibling: `dqiii8_knowledge.db` knowledge/vector. `dqiii8_history.db` and `dqiii8_metrics.db.old` are frozen post-migration artifacts)
- Writing to `agent_actions`: use `bin/core/action_log.py`'s shared helpers (`resolve_project_safe()`, `generate_request_id()`) — never hand-build the row. Column families and trigger contract: `.claude/rules/01_database_mutations.md`
- Hooks (15): `.claude/hooks/` | Skills (22): `.claude/skills/` | Agents (17): `.claude/agents/`
- Contextual rules (11): `.claude/rules_db/` — not read directly; injected per tool call by `rules_dispatcher.py` — 2 files minimum (`_ALWAYS`), 13 in the reachable ceiling case, drawn from both `.claude/rules_db/` and `.claude/rules/` (see `.claude/rules/02_hooks_and_permissions.md`). Counts on this line are validator-enforced (`check_claude_md_counts()` in `validate_rules_registry.py`).
- Entry: `bin/core/openrouter_wrapper.py` | Director: `bin/director.py`
- Dispatch (CC↔dqiii8): `bin/core/dispatch.py` — thin subprocess shim; sync + async via detached worker + atomic JSON envelope

> **Audit reports and audit docs are never committed — full stop.** Both `docs/audits/*.md` and
> `database/audit_reports/*.md` are gitignored with no negation. Their durability does
> NOT come from git — it comes from two independent off-VPS channels:
> `bin/tools/backup_audit_docs.sh` (mutual Netcup↔Hostinger rsync, dated snapshots, no
> `--delete` mirror) and `bin/tools/telegram_audit_backup.py` (per-file upload to a single
> allowlisted Telegram chat). Both read their targets/credentials from env vars only.
> Deleting a file under either path is effectively irreversible once both backups roll —
> treat these files with the same care as tracked ones even though `git status` won't see
> them.

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
- NEVER write to `.env` or `CLAUDE.md` — both are blocked paths, no exception, including a direct hand-authored edit (SSOT `.claude/rules/02_hooks_and_permissions.md` § Blocked paths). `database/schema_v2.sql` is the schema SSOT — additive changes only, via reviewed migrations; destructive schema changes → flag, never execute. (`database/schema.sql` no longer exists.)
- NEVER hardcode API keys — all keys via `os.environ.get("VAR")` only.
- NEVER commit `*.db` files — gitignored. Use `database/schema_v2.sql` for fresh installs.
- `ANTHROPIC_API_KEY` must be `""` in subprocess env when using Claude Code OAuth.
- Plans touching ≥3 modules OR with ambiguous scope → enter plan mode first, then
  run `/panel-review <plan-file>` before implementation (see `.claude/skills/panel-review/`).
- Destructive / irreversible actions (DROP, live-schema change, `rm -rf` of data) → STOP, notify, wait.
  Two exceptions already decided in code (`.claude/rules/02_hooks_and_permissions.md`): `rm -rf` of
  build/cache artifacts is auto-approved (`ALLOWED_DELETIONS`); `git push --force` is denied outright
  and user confirmation does not unblock it.
