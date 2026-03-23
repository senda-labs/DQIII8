# bin/ — DQIII8 Script Catalog

Active scripts only. Archived scripts live in `bin/archive/` (preserved, not deleted).

---

## Core Pipeline (20 scripts)

These scripts are imported or called directly by the pipeline. Do not move or rename without updating all callers.

| Script | Description |
|--------|-------------|
| `j.sh` | Main entry point — flag-based CLI (`--model`, `--status`, `--audit`, `--classify`) |
| `autonomous_loop.sh` | Autonomous session loop for VPS mode |
| `director.py` | Director v3 — routes prompts through the full DQ pipeline |
| `core/db.py` | SQLite wrapper — `get_db()`, `query()` |
| `core/embeddings.py` | Embedding helper — `get_embedding()` via nomic-embed-text (Ollama) |
| `core/notify.py` | Telegram notification sender |
| `core/ollama_wrapper.py` | Ollama API wrapper (local inference) |
| `core/openrouter_wrapper.py` | Multi-provider wrapper — Ollama / Groq / Anthropic 3-tier routing |
| `core/auth_watchdog.py` | Claude Code OAuth health check — cron */30min |
| `core/validate_env.py` | Validates required env vars at startup |
| `core/rate_limiter.py` | Per-provider rate limiting |
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
| `ui/jarvis_bot.py` | cron 08:00 daily | Telegram bot — primary user interface |
| `ui/dashboard.py` | on demand | Web dashboard |
| `ui/dashboard_security.py` | imported by dashboard.py | Dashboard auth layer |
| `ui/voice_handler.py` | imported by jarvis_bot.py | Voice message processing |
| `monitoring/analytics_collector.py` | cron 09:00 daily | Collects and stores usage analytics |
| `monitoring/benchmark_knowledge.py` | on demand | Benchmarks knowledge retrieval quality |
| `monitoring/telemetry.py` | called by nightly.sh | Opt-in telemetry sender |
| `monitoring/system_profile.py` | on demand | Captures system hardware/software profile |
| `agents/memory_decay.py` | cron 04:00 daily | Ages and prunes stale memory entries |
| `tools/auto_learner.py` | called by nightly.sh | Consolidates lessons from session history |
| `tools/auto_researcher.py` | cron Monday 06:00 | Weekly automated research sweep |
| `tools/sandbox_tester.py` | cron every 6h | Runs sandbox integration checks |
| `tools/lessons_consolidator.py` | cron monthly | Merges auto_learner output into long-term lessons |
| `tools/paper_harvester.py` | called by nightly.sh | Harvests and prunes research papers |
| `tools/github_researcher.py` | Telegram /research_status | Searches GitHub for relevant repos |
| `tools/gemini_export.py` | Telegram /dq | Exports modules for Gemini Pro review |

---

## Archived (21 scripts)

Moved to `bin/archive/` — preserved for reference or future phases.

| Archived path | Reason |
|---------------|--------|
| `archive/jal_common.py` | JAL framework — superseded by director.py |
| `archive/jal_critic.py` | JAL framework — superseded |
| `archive/jal_planner.py` | JAL framework — superseded |
| `archive/jal_scoring.py` | JAL framework — superseded |
| `archive/jarvis_architect.py` | Experimental architect agent — unused |
| `archive/orchestrator_loop.py` | Early orchestrator — replaced by autonomous_loop.sh |
| `archive/monitor.sh` | Simple monitor script — replaced by auditor_local.py |
| `archive/monitoring/audit_trigger.py` | Audit trigger — functionality merged into nightly.sh |
| `archive/monitoring/benchmark_amplification.py` | Amplification benchmark — one-off, not scheduled |
| `archive/monitoring/energy_tracker.py` | Energy tracker — not integrated into main pipeline |
| `archive/monitoring/ml_selector.py` | ML model selector — superseded by 3-tier routing |
| `archive/monitoring/quality_scorer.py` | Quality scorer — only used by benchmark_amplification.py |
| `archive/monitoring/subscription.py` | Subscription manager — unused |
| `archive/agents/knowledge_upload.py` | Knowledge uploader — functionality in knowledge_indexer |
| `archive/agents/memory_manager.py` | Memory manager — replaced by memory_decay.py |
| `archive/tools/handover.py` | **Phase 6B**: needed for stop.py → CLAUDE.md integration |
| `archive/tools/reconcile_errors.py` | Error reconciler — one-off tool |
| `archive/tools/setup_wizard.py` | Setup wizard — superseded by install.sh (planned) |
| `archive/tools/sqlite_mcp.py` | SQLite MCP server — not currently used |
| `archive/tools/verify_install.py` | **Phase 5**: base for install.sh (public repo) |
| `archive/ui/interactive_chat.py` | Interactive CLI chat — replaced by jarvis_bot.py |
