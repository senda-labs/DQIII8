# DQIII8 — System Integrity Audit
> Generated: 2026-03-24 | Tool: system-integrity-audit (PROMPT 6)
> Scope: DB, schemas, agent MDs, pipeline connections, hooks, crons, symlinks

---

## Summary Table

| Section | Status | Detail |
|---------|--------|--------|
| A. DB Health | ✅ | 47 tables, integrity OK, Prompt 5 tables present |
| B. Agent Coherence | ⚠️ | 27 agents — notation mismatches in .md model: field (cosmetic) |
| C. Pipeline Connections | ❌ | 7/8 connected — routing_feedback writer MISSING |
| D. Hooks Health | ✅ | 12/12 syntax OK, 0 hardcoded /root/jarvis paths |
| E. Crons Health | ✅ | 12/12 scripts found (false positive in checker — see notes) |
| F. Symlinks | ✅ | 2/2 correct, autoreporte_legacy correctly absent |

---

## PART A — Database Health

**Total tables: 47** | **Integrity: OK** | **FK check: OK**

### Row counts

| Table | Cols | Rows | Status |
|-------|------|------|--------|
| agent_actions | 31 | 11,010 | Active |
| agent_registry | 5 | 64 | Active |
| amplification_log | 19 | 728 | Active |
| audit_reports | 14 | 26 | Active |
| channel_stats | 9 | 0 | Empty — no writers |
| chat_messages | 5 | 6 | Active |
| chat_sessions | 2 | 1 | Active |
| code_metrics | 50 | 20 | Active |
| domain_enrichment | 7 | 5 | Active |
| error_log | 13 | 156 | Active |
| gemini_audits | 12 | 0 | Empty — no writers |
| github_research | 21 | 11 | Active |
| github_search_sessions | 10 | 6 | Active |
| historical_events | 17 | 290 | Active |
| instincts | 10 | 51 | Active |
| jal_conversations | 9 | 0 | Empty — writer exists |
| jal_error_patterns | 17 | 0 | Empty — writer exists |
| jal_error_taxonomy | 19 | 0 | Empty — writer exists |
| jal_objectives | 19 | 1 | Active |
| jal_scoring_snapshots | 20 | 0 | Empty — writer exists |
| jal_steps | 22 | 19 | Active |
| knowledge_benchmark_results | 25 | 301 | Active |
| knowledge_usage | 7 | 0 | ❌ Empty — NO writers |
| learned_approvals | 8 | 0 | Empty — no writers |
| learning_metrics | 6 | 139 | Active |
| loop_errors | 9 | 3 | Active |
| loop_objectives | 10 | 8 | Active |
| memory_links | 6 | 0 | Empty — writer exists |
| model_satisfaction | 10 | 0 | Empty — writer exists |
| morning_report | 12 | 2 | Active |
| objectives | 19 | 67 | Active |
| permission_decisions | 10 | 18 | Active |
| platform_config | 7 | 3 | Active |
| research_cache | 11 | 41 | Active |
| research_items | 10 | 17 | Active |
| resource_claims | 6 | 0 | Empty — no writers |
| routing_feedback | 8 | 0 | ❌ Empty — NO writers |
| scene_scripts | 17 | 61 | Active |
| session_memory | 6 | 6 | Active |
| sessions | 18 | 173 | Active |
| skill_metrics | 14 | 0 | Empty — no writers |
| spc_metrics | 9 | 880 | Active |
| sqlite_sequence | 2 | 29 | System |
| sync_state | 5 | 1 | Active |
| vault_memory | 17 | 717 | Active |
| vault_memory_archive | 11 | 0 | Empty — writer exists (memory_decay) |
| video_metrics | 26 | 0 | Empty — writer exists |
| video_outputs | 14 | 3 | Active |

### Prompt 5 tables
```
knowledge_usage  ✓ exists
routing_feedback ✓ exists
session_memory   ✓ exists
```

### Dead schema candidates (0 rows, 0 writers found)
| Table | Notes |
|-------|-------|
| channel_stats | YouTube channel analytics — YOUTUBE_API_KEY may be missing |
| gemini_audits | Gemini review flow — invoked manually via /gemini_export |
| learned_approvals | Permission approval learning — hook integration pending |
| resource_claims | Agent resource locking — never activated |
| skill_metrics | Skill performance tracking — no logger instrumented |

> `knowledge_usage` and `routing_feedback` are critical feedback tables (Prompt 5) that exist
> but have no writers — see ISSUES REMAINING.

### Core schemas: verified columns
- **agent_actions**: 31 cols incl. tier, domain, knowledge_chunks_used, energy_wh ✓
- **sessions**: 18 cols incl. compact_count ✓
- **error_log**: 13 cols incl. action_id FK ✓
- **instincts**: 10 cols incl. times_applied, times_successful, last_applied ✓
- **vault_memory**: 17 cols incl. decay_score, embedding, transferable ✓
- **routing_feedback**: 8 cols — prompt_hash, domain, tier_used, model_used, success, duration_ms ✓
- **knowledge_usage**: 7 cols — chunk_source, chunk_text_hash, domain, action_success, relevance_score ✓
- **session_memory**: 6 cols — session_id, role, content, domain ✓

---

## PART B — Agent MDs

**Total .md files: 27** | **In AGENT_ROUTING: 27 + "default" sentinel** | **In domain_agent_map: 19**

### Full agent inventory

| Agent | model: in .md | AGENT_ROUTING | KB | domain_map | DB actions |
|-------|--------------|---------------|----|------------|------------|
| ai-ml-specialist | groq/llama-3.3-70b-versatile | ✓ | NO | ✓ | 0 |
| algo-specialist | ollama/qwen2.5-coder:7b | ✓ | NO | ✓ | 0 |
| auditor | claude-sonnet-4-6 | ✓ | NO | — | 0 |
| biology-specialist | groq/llama-3.3-70b-versatile | ✓ | NO | ✓ | 0 |
| chemistry-specialist | groq/llama-3.3-70b-versatile | ✓ | NO | ✓ | 0 |
| code-reviewer | openrouter/openai/gpt-oss-120b:free | ✓ | NO | — | 0 |
| content-automator | ollama:qwen2.5-coder:7b | ✓ | YES | ✓ | 0 |
| data-specialist | groq/llama-3.3-70b-versatile | ✓ | NO | — | 0 |
| economics-specialist | groq/llama-3.3-70b-versatile | ✓ | NO | ✓ | 0 |
| finance-specialist | claude-sonnet-4-6 | ✓ | YES | ✓ | 0 |
| git-specialist | ollama:qwen2.5-coder:7b | ✓ | NO | — | 0 |
| history-specialist | groq/llama-3.3-70b-versatile | ✓ | NO | ✓ | 0 |
| language-specialist | groq/llama-3.3-70b-versatile | ✓ | NO | ✓ | 0 |
| legal-specialist | groq/llama-3.3-70b-versatile | ✓ | NO | ✓ | 0 |
| logic-specialist | groq/llama-3.3-70b-versatile | ✓ | NO | — | 0 |
| marketing-specialist | groq/llama-3.3-70b-versatile | ✓ | NO | ✓ | 0 |
| math-specialist | groq/llama-3.3-70b-versatile | ✓ | NO | ✓ | 0 |
| nutrition-specialist | groq/llama-3.3-70b-versatile | ✓ | NO | ✓ | 0 |
| orchestrator | claude-sonnet-4-6 | ✓ | NO | — | 0 |
| philosophy-specialist | groq/llama-3.3-70b-versatile | ✓ | NO | ✓ | 0 |
| physics-specialist | groq/llama-3.3-70b-versatile | ✓ | NO | ✓ | 0 |
| python-specialist | ollama:qwen2.5-coder:7b | ✓ | YES | ✓ | 3 |
| research-analyst | groq/llama-3.3-70b-versatile | ✓ | NO | — | 16 |
| software-specialist | groq/llama-3.3-70b-versatile | ✓ | NO | — | 0 |
| stats-specialist | groq/llama-3.3-70b-versatile | ✓ | NO | ✓ | 0 |
| web-specialist | ollama/qwen2.5-coder:7b | ✓ | NO | ✓ | 0 |
| writing-specialist | groq/llama-3.3-70b-versatile | ✓ | NO | ✓ | 0 |

### AGENT_ROUTING keys without .md
- `default`: MISSING .md — **intentional**, it's a sentinel value with no system prompt

### domain_agent_map.json agents without .md
- All 19 agents: **OK** ✓

### Model notation mismatches (.md vs AGENT_ROUTING)
Cosmetic only — AGENT_ROUTING is the authoritative routing source, .md `model:` field is informational.

| Format in .md | Format in AGENT_ROUTING | Agents |
|--------------|-------------------------|--------|
| `ollama:X` | `ollama/X` | content-automator, git-specialist, python-specialist |
| `model-name` (no provider) | `provider/model-name` | auditor, finance-specialist, orchestrator |

No functional routing errors — all agents resolve to the correct model.

### Agents not reachable via automatic pipeline
`logic-specialist`, `software-specialist` — exist in AGENT_ROUTING, not in domain_agent_map,
not in TASK_AGENT_MAP. Callable manually but never auto-selected.

---

## PART C — Pipeline Connections

| # | Connection | Status |
|---|-----------|--------|
| C1 | Entry → domain_classifier (line 682) | ✅ CONNECTED |
| C2 | Classifier → domain_agent_selector (line 778) | ✅ CONNECTED |
| C3 | Classifier → knowledge_enricher (line 712) | ✅ CONNECTED |
| C4 | Enricher → confidence_gate (line 732) | ✅ CONNECTED |
| C5 | Pipeline → intent_amplifier (line 696) | ✅ CONNECTED |
| C6 | Pipeline → working_memory (lines 660, 856, 886) | ✅ CONNECTED |
| C7 | Pipeline → DB logging / agent_actions (line 484) | ✅ CONNECTED |
| C8 | Pipeline → routing_feedback | ❌ NOT CONNECTED |

**C8 detail**: `routing_feedback` table was created by Prompt 5 schema migration and has
the correct schema (prompt_hash, domain, tier_used, model_used, success, duration_ms).
However, no code in `openrouter_wrapper.py` or any other module performs an INSERT.
The Prompt 5 `routing_analyzer.py` reads from `agent_actions` instead — routing_feedback
is designed to track per-prompt routing decisions separately but is currently unused.

---

## PART D — Hooks Health

**Total hooks: 12** | **Syntax OK: 12/12** | **Hardcoded /root/jarvis paths: 0**

| Hook | Syntax | jarvis hardcode | dqiii8 refs |
|------|--------|-----------------|-------------|
| permission_analyzer.py | ✅ OK | 0 | 7 |
| permission_request.py | ✅ OK | 0 | 5 |
| post_tool_use.py | ✅ OK | 0 | 2 |
| post_tool_use_failure.py | ✅ OK | 0 | 2 |
| postcompact.py | ✅ OK | 0 | 2 |
| pre_tool_use.py | ✅ OK | 0 | 1 |
| precompact.py | ✅ OK | 0 | 2 |
| semgrep_scan.py | ✅ OK | 0 | 2 |
| session_start.py | ✅ OK | 0 | 2 |
| stop.py | ✅ OK | 0 | 4 |
| subagent_start.py | ✅ OK | 0 | 4 |
| user_prompt_submit.py | ✅ OK | 0 | 2 |

All hooks correctly use `DQIII8_ROOT` env var or `/root/dqiii8` direct paths.
Migration to dqiii8 naming is complete across all hooks.

---

## PART E — Cron Jobs

**Total cron entries: 15** (12 python scripts, 1 bash, 2 find/cleanup)
**Broken scripts: 0** (see note)

| Script | Status | Schedule |
|--------|--------|----------|
| bin/monitoring/analytics_collector.py | ✅ | 09:00 daily |
| scripts/daily_topics.py (content-automation) | ✅ | 09:00 + 18:00 daily |
| bin/tools/auto_researcher.py | ✅ | 06:00 Mon |
| bin/tools/sandbox_tester.py | ✅ | every 6h |
| bin/agents/memory_decay.py | ✅ | 04:00 daily |
| bin/tools/lessons_consolidator.py | ✅ | 05:00 1st of month |
| bin/ui/jarvis_bot.py --morning-report | ✅ | 08:00 daily |
| bin/core/auth_watchdog.py | ✅ | every 30min |
| bin/monitoring/health_watchdog.py | ✅ | 07:00 daily |
| bin/monitoring/weekly_audit.py | ✅ | 08:00 Mon |
| bin/monitoring/routing_analyzer.py | ✅ | 06:00 Mon |
| bin/monitoring/knowledge_quality.py | ✅ | 07:00 1st of month |
| bin/nightly.sh | ✅ | 03:00 daily |
| find /tmp cleanup | ✅ | 03:00 daily |

**Note on daily_topics.py**: Automated checker reported BROKEN because it looked for the
file relative to `/root/dqiii8`. The cron runs with `cd /root/dqiii8/my-projects/content-automation`
so the relative path `scripts/daily_topics.py` resolves correctly — file confirmed present.

---

## PART F — Symlinks

| Symlink | Target | Status |
|---------|--------|--------|
| /root/jarvis | /root/dqiii8 | ✅ Correct |
| /root/content-automation-faceless | /root/dqiii8/my-projects/content-automation | ✅ Correct |
| /root/autoreporte_legacy | — | ✅ Absent (expected) |

Backward compatibility maintained. All external scripts using `/root/jarvis` paths continue
to work transparently via symlink.

---

## ISSUES REMAINING

> Everything below was identified but NOT fixed (audit-only per PROMPT 6 spec).

### CRITICAL

| # | Issue | File | Impact |
|---|-------|------|--------|
| C8 | `routing_feedback` table has no INSERT — routing feedback loop (Prompt 5) never fires | `bin/core/openrouter_wrapper.py` | Routing analytics accumulates zero data |
| C8b | `knowledge_usage` table has no INSERT — chunk-level quality tracking never fires | `bin/agents/knowledge_enricher.py` | `knowledge_quality.py` always reports 0 chunks |

### WARNING

| # | Issue | File | Impact |
|---|-------|------|--------|
| W1 | `logic-specialist`, `software-specialist` exist but are unreachable from automatic pipeline | `.claude/agents/*.md` | Dead agents — callable only with explicit `--agent` flag |
| W2 | `channel_stats` (0 rows, 0 writers) — YouTube stats never collected | DB only | Analytics gap |
| W3 | Model notation inconsistency: .md uses `ollama:X` while AGENT_ROUTING uses `ollama/X` | Various .md files | Cosmetic — no routing impact |

### INFO

| # | Issue | Notes |
|---|-------|-------|
| I1 | 5 tables with 0 rows and no code writers: `channel_stats`, `gemini_audits`, `learned_approvals`, `resource_claims`, `skill_metrics` | Intentional placeholders for future features |
| I2 | 5 jal_* tables empty (jal_conversations, jal_error_patterns, jal_error_taxonomy, jal_scoring_snapshots) | JAL subsystem writers exist but JAL never ran a session |
| I3 | `default` key in AGENT_ROUTING has no .md | Intentional — sentinel for "no agent specified" |

---

## Verdict

**The system is structurally sound.** After 5 prompts of audit + fixes:

- All 27 agent .md files are consistent with AGENT_ROUTING
- All 12 hooks are syntax-clean with no post-migration path errors
- DB integrity is clean (PRAGMA integrity_check: ok)
- All Prompt 5 tables exist with correct schemas
- Bloque 4.5 pipeline (classifier → selector → enricher → amplifier) is fully connected
- All cron scripts resolve to existing files

**Two actionable gaps remain** (both are missing INSERT statements):
1. `routing_feedback` writer in `openrouter_wrapper.py` — add after DB log call
2. `knowledge_usage` writer in `knowledge_enricher.py` — add when chunks are returned

These are the only items blocking the Prompt 5 feedback loops from collecting real data.
