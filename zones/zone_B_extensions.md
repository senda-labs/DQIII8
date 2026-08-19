# Zone B — Extensions (.claude/)
> Updated: 2026-06-16

---

## What it covers
All Claude Code extensions: agents, skills, hooks, rules, and the permission/rules system.

---

## Agents (17) — `.claude/agents/`

| Agent | Role |
|---|---|
| auditor | System audits |
| closing-specialist | Sales closing |
| code-reviewer | Code review |
| content-automator | Content generation |
| customer-accountant | Customer accounting |
| executor-lite | Lightweight task execution |
| explorer-lite | Lightweight exploration |
| finance-specialist | Financial analysis |
| git-specialist | Git operations |
| intl-writer | Internationalisation reports |
| invoice-extractor | Invoice data extraction |
| orchestrator | Multi-step task orchestration |
| python-specialist | Python dev |
| research-analyst | Research tasks |
| supplier-accountant | Supplier accounting |
| tax-auditor | Tax review |
| web-specialist | Web tasks |

---

## Skills (22) — `.claude/skills/`

| Skill | Trigger | Purpose |
|---|---|---|
| audit | `/audit` | Full system health audit |
| blue-team | — | Security defensive review |
| cdp-investigate | — | Chrome DevTools Protocol investigation |
| checkpoint | `/checkpoint` | Save session state |
| dispatch-agent | — | Hermes work-loop agent dispatch |
| drive-upload | `/drive-upload` | Upload intl-reports DOCXs to Google Drive via rclone |
| handover | `/handover` | Session handover note |
| instinct-status | `/instinct-status` | Instinct system check |
| intl-reports | `/intl-reports` | intl-reports batch pipeline |
| mobilize | `/mobilize` | Team mobilization |
| mode | `/mode` | Switch operating mode |
| panel-review | `/panel-review` | Adversarial multi-panel plan review |
| prompt-optimize | `/prompt-optimize` | Optimize a prompt |
| quality-gate | `/quality-gate` | Quality gate check |
| red-team | — | Security offensive review |
| security-cycle | — | Full security cycle |
| skill-create | `/skill-create` | Create a new skill |
| speckit | `/speckit` | Spec-Driven Development |
| svsi | `/svsi` | intl-reports semantic review |
| test-team | `/test-team` | Run test team |
| transcript-learn | — | Learn from transcript |
| weekly-review | `/weekly-review` | Weekly review |

**CRITICAL:** `tasks/audit/` path is hardcoded in red-team, blue-team, security-cycle skills. Never rename it.

---

## Hooks (15) — `.claude/hooks/`

| Hook | File | Fires on |
|---|---|---|
| pre_tool_use | pre_tool_use.py | Before any tool call |
| post_tool_use | post_tool_use.py | After any tool call |
| post_tool_use_failure | post_tool_use_failure.py | On tool failure |
| permission_analyzer | permission_analyzer.py | Permission checks |
| permission_request | permission_request.py | Permission requests |
| session_start | session_start.py | Session start |
| stop | stop.py | Session stop |
| precompact | precompact.py | Before context compact |
| postcompact | postcompact.py | After context compact |
| user_prompt_submit | user_prompt_submit.py | On user prompt |
| dq_compile_hook | dq_compile_hook.py | Opt-in plan compiler (DQ_COMPILE_HOOK=1) |
| subagent_start | subagent_start.py | Subagent start |
| rules_dispatcher | rules_dispatcher.py | Library imported by pre_tool_use.py — **not** wired to an event |
| semgrep_scan | semgrep_scan.py | Security scan — **not** wired to any event, currently invoked by nothing |
| rules_registry_introspect | rules_registry_introspect.py | Library — registry introspection for tests/validator |

15 = `.py` files in `.claude/hooks/` (the count CLAUDE.md pins). `run.sh` is the shell runner
`.claude/settings.json` invokes them through, not a hook itself. SSOT for which file fires on
which event: `.claude/settings.json`.

---

## Rules Engine — `.claude/rules/`

| File | Scope |
|---|---|
| `00_core_behavior.md` | Always loaded — zero-complacency, scope, cost-first |
| `01_database_mutations.md` | Any DB / SQL / sqlite3 work |
| `02_hooks_and_permissions.md` | Hooks, PermissionAnalyzer |
| `03_tiering_and_routing.md` | Tier table, routing decisions |
| `DYNAMIC.md` | Injected by rules_dispatcher.py at runtime |
| `.claude/rules_db/git-safety.md` | Git / Bash safety |
| `.claude/rules_db/dqiii8-error-prevention.md` | Recurring error prevention |

---

## Cross-zone Links
- Rules config → [[zone_H_config]]
- Audit outputs → [[zone_G_tasks]]
