# bin/ — DQIII8 Script Catalog

Active scripts only. `bin/archive/` no longer exists (its contents were fully removed, not
merely relocated — this table used to list it, see git history if you need the old paths).
[[tasks/FULL_SYSTEM_MAP|Full System Map]] is a historical snapshot (generated 2026-03-23,
not maintained since — read it as "how the tree looked then", not current state); the
rationale behind the script structure at the time is in
[[docs/architecture_decision_context_efficiency|ADR-001]].

---

## Core Pipeline (18 scripts)

These scripts are imported or called directly by the pipeline. Do not move or rename without updating all callers.

| Script | Description |
|--------|-------------|
| `j.sh` | Main entry point — flag-based CLI (`--model`, `--status`, `--audit`, `--classify`) |
| `autonomous_loop.sh` | Autonomous session loop for VPS mode |
| `director.py` | Director v3 — routes prompts through the full DQ pipeline |
| `core/db.py` | SQLite wrapper — `get_db()`, `query()` |
| `core/embeddings.py` | Embedding helper — `get_embedding()` via nomic-embed-text (Ollama) |
| `core/notify.py` | Telegram notification sender |
| `core/openrouter_wrapper.py` | Multi-provider wrapper — Ollama / Groq / Anthropic 3-tier routing |
| `core/auth_watchdog.py` | Claude Code OAuth health check — cron */30min |
| `core/validate_env.py` | Validates required env vars at startup |
| `core/db_security.py` | DB access control layer |
| `agents/domain_classifier.py` | Classifies prompts into 5 knowledge domains |
| `agents/hierarchical_router.py` | Routes classified prompts to the appropriate agent |
| `agents/intent_amplifier.py` | Expands prompt intent and assigns tier (1-3) |
| `agents/knowledge_enricher.py` | Injects relevant knowledge chunks into prompt context |
| `agents/knowledge_indexer.py` | Builds knowledge index (nomic-embed-text → index.json) |
| `agents/knowledge_search.py` | Cosine similarity search over index.json |
| `agents/template_loader.py` | Loads prompt templates (imported by intent_amplifier) |
| `monitoring/auditor_local.py` | Local health audit — scores system state 0-100 |

---

## Services (17 scripts)

Long-running services, scheduled jobs, and user-facing interfaces.

| Script | Schedule / Trigger | Description |
|--------|--------------------|-------------|
| `nightly.sh` | cron 03:00 daily | Nightly maintenance — consolidation, indexing, smoke tests, git commit |
| `ui/dqiii8_bot.py` | cron 08:00 daily | Telegram bot — primary user interface |
| `ui/dashboard.py` | on demand | Web dashboard |
| `ui/dashboard_security.py` | imported by dashboard.py | Dashboard auth layer |
| `tools/voice_handler.py` | imported by dqiii8_bot.py | Voice message processing |
| `monitoring/analytics_collector.py` | cron 09:00 daily | Collects and stores usage analytics |
| `monitoring/system_profile.py` | on demand | Captures system hardware/software profile |
| `agents/memory_decay.py` | cron 04:00 daily | Ages and prunes stale memory entries |
| `tools/auto_learner.py` | called by nightly.sh | Consolidates lessons from session history |
| `tools/auto_researcher.py` | cron Monday 06:00 | Weekly automated research sweep |
| `tools/sandbox_tester.py` | cron every 6h | Runs sandbox integration checks |
| `tools/lessons_consolidator.py` | cron monthly | Merges auto_learner output into long-term lessons |
| `paper_harvester.py` | called by nightly.sh | Harvests and prunes research papers |
| `tools/github_researcher.py` | Telegram /research_status | Searches GitHub for relevant repos |
| `tools/gemini_export.py` | Telegram /dq | Exports modules for Gemini Pro review |
| `tools/sqlite_mcp.py` | MCP server | SQLite MCP server — serves dqiii8.db over MCP protocol |
| `tools/setup_gitleaks_hook.sh` | on demand | Installs gitleaks pre-commit hook on VPS — run once per environment |

---

_Ver también: [[README]] · [[CLAUDE]] · [[tasks/FULL_SYSTEM_MAP|Full System Map]]_
