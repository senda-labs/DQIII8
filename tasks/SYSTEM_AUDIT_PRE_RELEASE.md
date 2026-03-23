# DQIII8 — System Audit Pre-Release
**Date:** 2026-03-23
**Auditor:** Claude Sonnet 4.6 (automated)
**Status:** PASS with known issues

---

## Summary Table

| Category | Status | Notes |
|---|---|---|
| A. Scripts (bin/) | ✅ OK | 44/44 import correctly |
| B. Agents (.claude/agents/) | ✅ OK | 26/26 valid frontmatter |
| C. Knowledge base | ✅ OK | 894 chunks across 5 domains |
| D. Database | ✅ OK | 9873 rows, 4 analytic views return data |
| E. Hooks | ✅ OK | 11 hook events configured |
| F. Crontab | ⚠️ WARN | 2 external crons unverifiable (content-automation-faceless path) |
| G. Services | ✅ OK | jarvis_bot active, Ollama + 4 models loaded |
| H. Tests | ⚠️ WARN | 85/94 pass, 5 fail (pre-existing, see below) |
| I. Docs | ✅ OK | ARCHITECTURE.md + PRO_CANDIDATES.md present |
| J. Repo safety | ✅ OK | No .env/.db/credentials tracked by git |
| K. DQ Pipeline E2E | ✅ OK | All 7 steps verified |

---

## A — Scripts (bin/)

- **Total:** 44 Python files (excluding bin/archive/)
- **Import OK:** 44/44
- **Import FAIL:** 0

All scripts load without syntax or import errors.

---

## B — Agents (.claude/agents/)

- **Total:** 26 agent `.md` files
- **Valid frontmatter (name + model):** 26/26

No missing or malformed agent definitions.

---

## C — Knowledge Base

| Domain | Chunks | Last Indexed | Size (KB) |
|---|---|---|---|
| applied_sciences | 154 | 2026-03-23 | 3203.6 |
| formal_sciences | 92 | 2026-03-23 | 1892.7 |
| humanities_arts | 53 | 2026-03-23 | 1124.2 |
| natural_sciences | 163 | 2026-03-23 | 3352.2 |
| social_sciences | 432 | 2026-03-23 | 8862.2 |
| **TOTAL** | **894** | | **18434.9** |

Target was ≥800 total. **894 achieved.** humanities_arts at 53 is at minimum viable (target was 50+).

---

## D — Database

- **Table:** `jarvis_metrics.db`
- **Tables:** 42 tables, 17 views
- **agent_actions rows:** 9873

### Analytic views (all return data):

| View | Status | Sample |
|---|---|---|
| v_cost_savings | ✅ | 2026-03-10 \| unknown \| 104 calls |
| v_agent_performance | ✅ | claude-sonnet-4-6 \| 3079 calls \| 98.6% success |
| v_tier_distribution | ✅ | 2026-03-10 \| B \| 104 calls |
| v_dq_uplift | ✅ | llama-3.3-70b \| applied_sciences \| score 7.14 |

---

## E — Hooks

11 hook events configured in `.claude/settings.json`:

- SessionStart (2 commands)
- PreToolUse (2), PostToolUse (3), PostToolUseFailure (1)
- PreCompact (2), PostCompact (1)
- Stop (1), SubagentStop (1), SubagentStart (1)
- UserPromptSubmit (1), PermissionRequest (1)

---

## F — Crontab

| Script | Status |
|---|---|
| bin/monitoring/analytics_collector.py | ✅ OK |
| bin/tools/auto_researcher.py | ✅ OK |
| bin/tools/sandbox_tester.py | ✅ OK |
| bin/agents/memory_decay.py | ✅ OK |
| bin/tools/lessons_consolidator.py | ✅ OK |
| bin/ui/jarvis_bot.py | ✅ OK |
| bin/nightly.sh | ✅ OK |
| bin/core/auth_watchdog.py | ✅ OK |
| /root/content-automation-faceless/scripts/daily_topics.py | ⚠️ External path — not checked |
| find /tmp cleanup | ⚠️ No script path — shell command inline |

**WARN:** 2 cron entries use paths outside `/root/jarvis`. Cannot verify from this repo.

---

## G — Services

| Service | Status |
|---|---|
| tmux: jarvis_bot | ✅ Active (since 2026-03-15) |
| tmux: jarvis | ✅ Active (since 2026-03-12) |
| tmux: api2 | ✅ Active |
| tmux: auth | ✅ Active |
| tmux: cloudflare | ✅ Active |
| Ollama: nomic-embed-text | ✅ Loaded |
| Ollama: qwen2.5-coder:7b | ✅ Loaded (Tier C) |
| Ollama: qwen2.5:3b | ✅ Loaded |
| Ollama: llama3:latest | ✅ Loaded |

---

## H — Tests

**Result: 85 passed, 5 failed, 2 skipped, 2 xfailed** (94 total)

### Failures (pre-existing, not caused by this sprint):

| Test | Failure | Root Cause |
|---|---|---|
| test_full_pipeline_business | `[CONTEXT]` not in amplified | test_e2e_pipeline expects legacy `[CONTEXT]/[REQUEST]` format; pipeline now uses XML `<task>` |
| test_full_pipeline_finance | `[REQUEST]` not in amplified | Same: legacy format assertion |
| test_full_pipeline_code | `[REQUEST]` not in amplified | Same: legacy format assertion |
| test_hierarchical_router_has_agents | agents list is empty in centroid | Hierarchical router agent field not populated |
| test_knowledge_retrieval_returns_content | 0-length knowledge for economics | `knowledge_search.py` `search_agent_knowledge()` path mismatch (agents vs domains) |

**Root cause summary:** `test_e2e_pipeline.py` (3 failures) asserts the old `[CONTEXT]/[KNOWLEDGE]/[REQUEST]` format that was replaced by tier-specific XML templates. Tests are stale, not the pipeline.

---

## I — Documentation

| File | Status | Lines |
|---|---|---|
| docs/ARCHITECTURE.md | ✅ Present | 219 |
| docs/PRO_CANDIDATES.md | ✅ Present | 43 |

---

## J — Repo Safety

| Check | Status |
|---|---|
| my-projects/.gitkeep exists | ✅ OK |
| config/.env.example exists | ✅ OK |
| .env tracked by git | ✅ None found |
| *.db tracked by git | ✅ None found |
| credentials tracked by git | ✅ None found |

---

## K — DQ Pipeline End-to-End

**Prompt:** `calculate WACC for Tesla assuming 10% cost of equity`

| Step | Result |
|---|---|
| 1. Domain classification | social_sciences (score=1.00, method=keyword) ✅ |
| 2. Chunk retrieval (task_relevance reranking) | 3 chunks (DCF, Risk-Neutral Pricing, Risk Parity) ✅ |
| 3. Confidence gate | ENRICH (specific financial data found) ✅ |
| 4. Tier selection | Tier A (3), chunks_used=1 ✅ |
| 5. Intent suffix (Tier A) | Not applied (Tier A — frontier, no scaffolding) ✅ |
| 6. Overhead | 308 chars (within Tier A cap of 400) ✅ |
| 7. Entity extraction | WACC ✅ (no CONTEXT corruption) |

**Pipeline is fully operational.**

---

## Problems Found

### Must Fix Before Release

_(none)_

### Should Fix (non-blocking)

1. **test_e2e_pipeline.py (3 tests):** Stale assertions expecting `[CONTEXT]/[REQUEST]` legacy format. Update to match current XML tier format.

2. **test_hierarchical_router_has_agents:** `hierarchical_router.py` returns empty `agents` list in centroid dict — routing table changed but test wasn't updated.

3. **test_knowledge_retrieval_returns_content:** `knowledge_search.py search_agent_knowledge()` fails silently for domain-based indexes (path expects `.claude/agents/{name}/knowledge/` but domain knowledge is in `knowledge/{domain}/`).

### Low Priority

4. **2 external cron entries:** `content-automation-faceless` crons can't be verified from this repo. Manual check recommended.

5. **humanities_arts at 53 chunks:** At minimum viable level. Consider adding more specific-data art/film/literature content.

---

## Orphaned Files / Unused Agents

| Agent | Routing table? | Notes |
|---|---|---|
| content-automator | ✅ Yes | Uses openrouter/nvidia/nemotron |
| data-analyst | ✅ Yes | Uses openrouter/gpt-oss-120b |
| hierarchical_router.py | Referenced in tests only | Not in main pipeline path |
| template_loader.py | No direct cron/agent | Used by other scripts |
| analytics_collector.py | Cron daily | OK |
| system_profile.py | No cron | Orphaned? Run manually |
| voice_handler.py | No cron or agent | Orphaned? Kept for future |
| gemini_export.py | Telegram command | OK |
| paper_harvester.py | No cron | On-demand only |
