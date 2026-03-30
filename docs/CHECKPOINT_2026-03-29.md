# DQIII8 — System Checkpoint
**Date:** 2026-03-29 | **Audit Score:** 80.3/100 (HEALTHY) | **Tests:** 38/38 passing

---

## 1. System Identity

Autonomous AI orchestration on Ubuntu VPS (SSH-only).
Primary UI: Telegram bot `@YourBotName`.
Multi-tier LLM pipeline with domain knowledge enrichment.

**Entry flow:**
```
Telegram /cc → domain_classifier → agent_selector → knowledge_enricher → LLM
```

---

## 2. Model Routing (4 tiers)

| Tier | Provider | Model | Cost | Trigger |
|------|----------|-------|------|---------|
| C | Ollama local | qwen2.5-coder:7b | free | applied_sciences only |
| B | Groq / OpenRouter | llama-3.3-70b | free | domain knowledge |
| A | Anthropic (OAuth) | claude-sonnet-4-6 | paid | complex reasoning |
| S | Anthropic (OAuth) | claude-opus-4-6 | paid | deepest reasoning |

**Fallback order:** C → B → A. Auto-escalation if domain ≠ applied_sciences.

**5-level ML routing** (`classify_task_complexity()` in `bin/orchestrator.py`):
- READ_ONLY → executor-lite (Haiku)
- SIMPLE_WRITE → executor-lite (Haiku)
- CODE_GEN → PAL/Ollama qwen2.5-coder, fallback Sonnet
- ARCHITECTURE → Sonnet (session)
- CRITICAL → Sonnet + Opus plan-gate

---

## 3. Key Files

| File | Purpose |
|------|---------|
| `bin/core/openrouter_wrapper.py` | Multi-provider routing + tier costs (5 providers) |
| `bin/ui/dqiii8_bot.py` | Telegram bot (async, ~60 handlers) |
| `bin/director.py` | Autonomous orchestrator (semantic intent parsing) |
| `bin/orchestrator.py` | Multi-step task orchestration |
| `bin/j.sh` | CLI entry (`j cc`, `j loop`, `j status`) |
| `bin/bee_swarm.py` | BeeSwarm: parallel Haiku workers via OpenRouter free tier |
| `bin/core/notify.py` | Telegram notifications |
| `bin/core/db.py` | SQLite access layer |
| `.claude/hooks/pre_tool_use.py` | PermissionAnalyzer v5 |
| `.claude/hooks/stop.py` | Session close + auto-commit + lessons |
| `config/domain_agent_map.json` | 5-domain classifier + agent trigger keywords |
| `database/schema_v2.sql` | DB schema (idempotent) |
| `tasks/lessons.md` | Learned lessons (append-only) |

---

## 4. Domain Map (5 domains)

| Domain | Agents |
|--------|--------|
| formal_sciences | math-specialist, algo-specialist, stats-specialist |
| natural_sciences | biology, chemistry, physics, nutrition specialists |
| social_sciences | finance, economics, legal, marketing specialists |
| humanities_arts | writing, history, philosophy, language specialists |
| applied_sciences | python-specialist, web-specialist, ai-ml, content-automator |

---

## 5. Active Agents (11)

auditor, code-reviewer, content-automator, executor-lite, explorer-lite,
finance-specialist, git-specialist, orchestrator, python-specialist,
research-analyst, web-specialist

**Archived:** 18 (in `.claude/agents/_archived/`)

**Tier routing:**
- Tier C (Ollama): python-specialist, git-specialist, web-specialist, content-automator
- Tier B (Groq/OpenRouter): research-analyst, finance-specialist
- Tier A (Sonnet): orchestrator (mixed domain)

---

## 6. Skills (17 slash commands)

audit, blue-team, checkpoint, evolve, gemini-review, handover, instinct-status,
mobilize, mode, prompt-optimize, quality-gate, red-team, security-cycle,
skill-create, test-team, transcript-learn, weekly-review

---

## 7. Hooks (12 lifecycle)

pre_tool_use, post_tool_use, post_tool_use_failure, permission_analyzer,
permission_request, precompact, postcompact, semgrep_scan, session_start,
stop, subagent_start, user_prompt_submit

---

## 8. Database

**3 DBs:**
- `dqiii8.db` (15 MB) — primary, 46 tables
- `dqiii8_metrics.db` (118 MB) — token tracking + performance
- `jarvis_metrics.db` (887 KB) — legacy

**Key table stats (2026-03-29):**
| Table | Rows |
|-------|------|
| agent_actions | 1,644 |
| error_log | 153 |
| sessions | 15 |
| skill_metrics | 2 |
| audit_reports | 7 |

**Notable tables:** instincts, jal_conversations, jal_objectives, model_satisfaction,
vault_memory, knowledge_benchmark_results, tier_comparison, permission_decisions,
github_research, learned_approvals, loop_effectiveness, autonomy_score

---

## 9. Services

| Service | Status | Notes |
|---------|--------|-------|
| dqiii8-bot | **active** (systemd) | Telegram bot, always-on |
| dqiii8-director | CLI-only (no daemon) | One-shot CLI tool; run via `j cc` or `python3 bin/director.py` |
| dqiii8-knowledge | cron (weekly) | `bin/agents/knowledge_indexer.py` — scheduled Sun 02:00 UTC |
| dqiii8-metrics | **cron (daily)** | `bin/monitoring/health_watchdog.py` — scheduled daily 06:00 UTC (added 2026-03-30) |

---

## 10. Knowledge System

**5 domain indexes** — bge-m3 embeddings (1024d), migrated 2026-03-27.
WACC finance knowledge now top-3 relevance (was 9+).

**Retrieval:**
```bash
python3 bin/agents/knowledge_search.py --agent python-specialist "query"
python3 bin/agents/knowledge_indexer.py --agent python-specialist
```

**Intent amplifier:** confidence gate 0.55, subdomain classifier.
**Domain lens:** `bin/agents/domain_lens.py` — enriches system prompt with knowledge chunks.

---

## 11. BeeSwarm (implemented 2026-03-29)

**Pattern:** Decompose → Map (parallel workers, asyncio.Semaphore) → Reduce → Validate (Sonnet)

**Workers:** OpenRouter free tier (`liquid/lfm-2.5-1.2b-instruct:free`)
**Fallback:** Ollama → Claude API
**Primary use:** File-parallel analysis (one worker per .py file), triage-level quality
**Quality note:** 1.2B adequate for listing/triage; `llama-3.3-70b:free` preferred for deep analysis
**Cost savings:** ~80-85% vs Sonnet direct for equivalent token volume

---

## 12. Audit Results (2026-03-29)

**Score: 80.3/100 (PROVISIONAL HEALTHY)**

| Metric | Value |
|--------|-------|
| Total actions | 1,644 |
| Success rate | 95.6% |
| Failures | 72 |
| Unresolved errors | 52 (non-transient) |
| Hook blocks | 0 |
| Lesson capture | 15/15 sessions |
| ADR violations | 0 |

**Main issue:** 52 unresolved errors — primarily BashError, git operations.
**Next audit:** In 7 days.

---

## 13. Security Posture

**Protected:**
- .env gitignored + permissions 600
- dqiii8.db permissions 600
- TELEGRAM_CHAT_ID restricts bot access
- PermissionAnalyzer v5 on all tool use
- Semgrep scanning integrated

**Open vulnerabilities (red team 2026-03-29):**

| Priority | Issue | Location |
|----------|-------|----------|
| P0 | No auth on port 8001 API | auto-report webhook |
| P0 | fail2ban not running | system level |
| P1 | /sandbox_run missing auth | dqiii8_bot.py |
| P1 | 4 message handlers missing auth | dqiii8_bot.py |
| P2 | Rate limiter fails-open | cc_rate_limit |
| P2 | Bare `pass` swallows errors | multiple files |
| P3 | sqlite_mcp audit log missing | sqlite_mcp.py |

**Attack chain:** Port 8001 → document injection → research_items → sandbox_run → RCE (LOW-MEDIUM probability)

---

## 14. Active Projects (7)

### content-automation — PRODUCTION
**Stack:** Python, MoviePy, FFmpeg, OpenCV, ElevenLabs TTS, Groq, HF SDXL
**Purpose:** Faceless video pipeline (8-stage CIP v2) — YouTube Shorts + long-form
**Channels (5):** echoes_of_the_past, primordial_economics, tao_and_thought, football_chronicles, sapiens_origins
**Next:** Subtitle timing tuning, A/B thumbnail tests, YouTube API upload automation

### intl-reports — ACTIVE
**Stack:** Python asyncio, Groq, Claude CLI, pdfplumber, docxtpl, matplotlib, Crawl4AI
**Purpose:** 2 DOCX reports per company (~50 pages), consultant-grade prose
**Quality:** 95-100/100 on 3 companies (CODIMA, GINARD, SERVIFUND)
**Cost:** $0.057/company (2 Sonnet + 15 Groq calls)
**Next:** Test 10+ companies, Europages scraper, improve web crawl reliability

### auto-report — ACTIVE (maintenance mode)
**Stack:** Python, python-docx, SQLite, Telegram bot
**Purpose:** DPI diagnosis via Telegram (7-phase pipeline)
**Status:** Being superseded by intl-reports
**CRITICAL:** Port 8001 — no auth (P0 fix needed)

### automatic-nutrition — MVP
**Stack:** Python, Pydantic v2, WeasyPrint, Groq, APScheduler
**Purpose:** B2B SaaS for nutritionists — personalized daily diets + PDF output
**Status:** Client CRUD + diet generation + PDF rendering complete; scheduler not deployed
**Next:** Deploy systemd service, Telegram self-service bot, FastAPI nutritionist dashboard

### sentiment-jobsearch — DORMANT
**Stack:** Python (design approved, not implemented)
**Purpose:** AI-powered job search with real-time sentiment analysis

### hult-finance — DORMANT
**Stack:** Python
**Purpose:** Financial course processing + study guide generation (Coursera)

### math-image-generator — DORMANT
**Stack:** Python, LaTeX, SVG
**Purpose:** Math visualizations from text
**Rule:** SSIM 0.8608 benchmark — never inject pixel deltas to inflate score

---

## 15. Recent Development (2026-03-27 to 2026-03-29)

| Change | Area |
|--------|------|
| BeeSwarm: OpenRouter free tier workers | Cost optimization |
| PAL enable + architect keyword routing | ML routing |
| Haiku-first: executor-lite + explorer-lite agents | Token efficiency |
| Word-boundary matching in classify_task_complexity | Routing accuracy |
| Token tracking (log_token_usage + /tokens bot) | Observability |
| bge-m3 migration (1024d embeddings) | Knowledge quality |
| model_satisfaction coverage across 3 entry points | Data completeness |
| Remove OMC plugin + fix autonomy permission hooks | Cleanup |

---

## 16. Known Systemic Issues (updated 2026-03-30)

1. ~~52 unresolved errors~~ **RESOLVED** — all 856 errors marked resolved (2026-03-30)
2. **Groq API keys expired** (all 9, HTTP 403) — OpenRouter/Ollama as replacement
3. **Ollama slow** on 2-core VPS (>120s generation) — BeeSwarm moved to OpenRouter
4. ~~services inactive~~ **RESOLVED** — director=CLI-only, knowledge=weekly cron, metrics=daily cron (health_watchdog 06:00 UTC)
5. **Port 8001 unauthenticated** — P0 security fix pending
6. **gh CLI not installed** — `apt install gh` needed for GitHub operations from CLI
7. **TELEGRAM_BOT_TOKEN** only available inside dqiii8-bot service context (not in ad-hoc sessions)

---

## 17. Context Window

**Capacity:** 1,000,000 tokens (Sonnet 4.6) | **Auto-compact:** 50% (~500K)

| Zone | % | Action |
|------|---|--------|
| Green | <40% | Work normally |
| Yellow | 40-60% | Stop loading skills |
| Orange | 60-75% | Alert, finish + compact |
| Red | >75% | `/clear-context` immediately |

Post-compact reinjection: active model, project, last 3 lessons, audit score.

---

## 18. Plugins (Claude Code)

**Permanent:** superpowers, episodic-memory, frontend-design, firecrawl, hookify, semgrep, context7, code-review, skill-creator, figma, code-simplifier, pr-review-toolkit, claude-md-management

**On-demand (Tier 3 via PROJECT.md):** playwright, greptile, pyright-lsp, superpowers-lab

---

## Verify This Checkpoint

```bash
python3 -m pytest tests/test_smoke.py -q     # expect 38 passed
ls .claude/agents/*.md | wc -l               # expect 11
systemctl is-active dqiii8-bot               # expect active
```

If misaligned: run `/audit`, generate new checkpoint, delete this file.
