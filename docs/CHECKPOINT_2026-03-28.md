# DQIII8 — System Checkpoint 2026-03-28

> Complete system context for session continuity with Opus 4.6 (1M context).
> Generated after full audit + fix session. All tests passing (113/113).

---

## 1. What is DQIII8?

DQIII8 is an autonomous AI orchestration system running on a VPS (Ubuntu, SSH-only). It routes user queries through a multi-tier LLM pipeline with domain-specific knowledge enrichment, 27 specialist agents, and Telegram as the primary UI. The "DQ" stands for "Domain-Quality" — the enrichment pipeline that boosts LLM responses with curated knowledge chunks.

**Core philosophy:** Cheapest tier first. Local Ollama → free cloud (Groq) → paid Claude only for finance/architecture/orchestration.

---

## 2. Infrastructure

| Component | Detail |
|-----------|--------|
| VPS | Ubuntu Linux 6.8.0-106 |
| SSH | Key-only, PasswordAuth=no, PermitRootLogin=prohibit-password |
| Firewall | UFW — port 22 only, all others DENY |
| fail2ban | Active, sshd jail |
| Ollama | localhost:11434 — bge-m3 (1.2GB), qwen2.5-coder:7b (4.7GB), qwen2.5:3b, llama3 |
| Dashboard | FastAPI on 127.0.0.1:8080 (localhost-only) |
| Database | SQLite + sqlite-vec at `database/dqiii8.db` (79 tables) |
| Claude Code | v2.1.86, OAuth via `~/.claude/.credentials.json` |
| Python | 3.12.3 |

---

## 3. Model Routing (4 tiers, 7 providers)

### Providers

| Provider | Base URL | Auth | Status |
|----------|----------|------|--------|
| ollama | localhost:11434/v1 | None | Active |
| groq | api.groq.com/openai/v1 | GROQ_API_KEY | Active |
| openrouter | openrouter.ai/api/v1 | OPENROUTER_API_KEY | Active |
| github | models.inference.ai.azure.com/v1 | GITHUB_TOKEN | Active |
| pollinations | text.pollinations.ai/openai | None | Active |
| anthropic | api.anthropic.com/v1 | ANTHROPIC_API_KEY (missing) → fallback `claude -p` CLI | Active via CLI |

**Note:** llm7 was removed on 2026-03-28 (0% success rate over 40 calls).

### Tier Map

| Tier | Provider | Model | Cost | When |
|------|----------|-------|------|------|
| C | ollama | qwen2.5-coder:7b | $0 | Code, refactor, debug, git |
| B | groq | llama-3.3-70b-versatile | $0 | Review, analysis, research, domain knowledge |
| A | anthropic | claude-sonnet-4-6 | ~$0.01-0.05 | Finance, architecture, orchestration |
| S | anthropic | claude-opus-4-6 | ~$0.15-0.50 | /mobilize, multi-agent, system design |

### Agent Routing (27 active agents)

**Tier C (local, code-only):**
python-specialist, git-specialist, web-specialist, algo-specialist, content-automator

**Tier B (Groq free):**
ai-ml-specialist, biology-specialist, chemistry-specialist, data-specialist, economics-specialist, history-specialist, language-specialist, legal-specialist, logic-specialist, marketing-specialist, math-specialist, nutrition-specialist, philosophy-specialist, physics-specialist, software-specialist, stats-specialist, writing-specialist, research-analyst, code-reviewer

**Tier A (Anthropic — via claude CLI fallback):**
finance-specialist, auditor, orchestrator

**Default agent:** groq/llama-3.3-70b-versatile (changed from step-3.5-flash on 2026-03-28)

### Fallback Chain
```
ollama → groq → openrouter → github → pollinations
groq → openrouter → github → pollinations
openrouter → groq → github → pollinations
anthropic → groq → openrouter → pollinations
github → groq → pollinations
```

### Tier Escalation
Tier C agents outside `_TIER_C_AGENTS` set auto-escalate to Tier B when domain ≠ applied_sciences.

---

## 4. DQ Pipeline (8 steps)

### Entry Points
1. **CLI:** `python3 bin/core/openrouter_wrapper.py --agent {agent} "prompt"`
2. **Telegram:** `/cc <prompt>` → `bin/ui/jarvis_bot.py` → `_run_claude()`
3. **Director:** `python3 bin/director.py "request"` (autonomous mode)
4. **Dashboard:** POST `127.0.0.1:8080/api/chat` → stream response

### Pipeline Flow

```
User prompt
    ↓
[1] domain_classifier.py → classify_domain(prompt)
    Method: keyword match (≥2 hits) → embedding fallback (bge-m3 centroids)
    Output: (domain, confidence, method) — e.g. ("applied_sciences", 1.0, "keyword")
    ↓
[2] subdomain_classifier.py → classify_subdomain(prompt, domain)
    Method: keyword match within parent domain (0ms, no network)
    Output: subdomain string — e.g. "ai_ml", "corporate_finance"
    ↓
[3] hierarchical_router.py → classify_hierarchical(prompt, embedding)
    Method: 3-level softmax (τ₁=0.25, τ₂=0.20, τ₃=0.25)
    Output: active centroids, agents, chunk allocations
    ↓
[4] domain_agent_selector.py → select_domain_agent(prompt, domain)
    Method: keyword triggers from config/domain_agent_map.json
    Output: (agent_name, system_prompt from .claude/agents/{name}.md)
    ↓
[5] knowledge_enricher.py → get_relevant_chunks(prompt, domain, ...)
    Method: Hybrid search (vector + FTS5 + graph) → RRF merge → composite rerank
    Thresholds: cosine ≥ 0.55, composite ≥ 0.30, max 5 chunks
    Output: list[dict] with text, score, source, subdomain
    ↓
[6] confidence_gate.py → should_enrich(prompt, domain, chunks, tier)
    Rules: Tier C always enrich; Tier A skip if max_score < 0.55; skip if no specific data
    Output: bool
    ↓
[7] intent_amplifier.py → amplify(prompt, domain=, chunks=)
    Tier C: XML tags + 1 truncated chunk + CoT (30-600 chars overhead)
    Tier B: Role assignment + reference block ≤2500 chars + CoT if formula
    Tier A: Raw data only, no scaffolding (0-400 chars overhead)
    Output: {"amplified": str, "tier": int, "chunks_used": int, ...}
    ↓
[8] stream_response(provider, model, amplified_prompt, system_prompt)
    Anthropic without API key → _stream_via_claude_cli() (OAuth fallback)
    Other providers → urllib streaming to stdout
    Output: (text, tokens_in, tokens_out, success)
```

---

## 5. Knowledge System

### Chunks per domain (all bge-m3, 1024-dim)

| Domain | Chunks | Index Size |
|--------|--------|------------|
| social_sciences | 699 | 19 MB |
| natural_sciences | 441 | 12 MB |
| formal_sciences | 334 | 9 MB |
| applied_sciences | 155 | 4.3 MB |
| humanities_arts | 55 | 1.5 MB |
| **finance-specialist (agent)** | **22** | **0.6 MB** |
| **Total** | **1,706** | **~46 MB** |

### Hybrid Search (3 signals + RRF)

| Signal | Weight | Source |
|--------|--------|--------|
| Vector (cosine KNN) | 1.0 | sqlite-vec on bge-m3 embeddings |
| Keyword (FTS5 BM25) | 0.7 | chunks_fts full-text index |
| Graph (relations) | 0.5 | relations table (placeholder) |

### Composite Reranking
```
composite = base_cosine × 0.60 + subdomain_match × 0.25 + keyword_overlap × 0.15

subdomain_match: 1.0 exact, 0.3 parent domain, 0.0 different
keyword_overlap: matching_terms / total_query_terms (4+ char terms only)
```

### Project-Scoped Retrieval (B10 — new 2026-03-28)
- `get_relevant_chunks(..., project="auto-report")` boosts chunks with source prefix `user:{project}` by 1.2x
- `openrouter_wrapper.py` auto-detects project from `--project` arg or CWD containing `my-projects/{name}`
- Ingest: `python3 bin/tools/knowledge_harvester.py --ingest --project auto-report file.md`

---

## 6. Temporal System

| Component | Schedule | Function |
|-----------|----------|----------|
| fact_extractor.py | cron every 4h | Extract entity-predicate-value triples from text via Groq |
| instinct_evolver.py | cron Monday | Cluster high-confidence instincts (>0.7) into skill drafts |
| memory_decay.py | cron daily 4am | Decay vault_memory scores (0.95^weeks), archive if <0.1 |
| chunk_freshness_reviewer.py | cron Sun 3am | Review 100 oldest chunks for staleness |
| knowledge_harvester.py | cron Sun 2am | Harvest up to 20 new knowledge items from RSS feeds |

### Memory Decay Formula
```
new_score = decay_score × 0.95^weeks_elapsed
archive_threshold = 0.1
access_boost = +0.2 per access (capped at 1.0)
```

### Instinct Reinforcement
```
Unused 30+ days → confidence - 0.02/cycle (floor 0.1)
times_successful > 10 AND success_rate > 0.8 → confidence + 0.05/cycle (cap 1.0)
Fast-path threshold: confidence > 0.7
```

---

## 7. Telegram Bot (`bin/ui/jarvis_bot.py`)

### Commands

| Command | Purpose |
|---------|---------|
| `/start` | Initialize |
| `/status [project]` | System/project status |
| `/cc <prompt>` | Execute via Claude Code (rate: 10/hr) |
| `/cc_status` | Auth, version, rate limit |
| `/loop [project] [cycles] [tier]` | Autonomous loop via director.py |
| `/stop` | Stop autonomous loop |
| `/audit` | System health audit |
| `/dq` | DQ metrics summary |
| `/tasks` | List active tasks |
| `/task <id>` | Task detail |
| `/output <id>` | Task output |
| `/kill <id>` | Terminate task |
| `/score` | Satisfaction scores |
| `/logs` | Recent errors |
| `/sandbox_run` | Execute sandbox tester |
| `/voice on\|off` | Toggle TTS |
| `/auth_status`, `/auth_test`, `/auth_update` | OAuth management |
| `/images [query]` | Image generation |
| `/research_status` | Research progress |
| `/integrar <id>` | Mark research INTEGRADO |
| `/rechazar <id>` | Mark research RECHAZADO |

### Media Handlers
- **Photo upload** → image analysis
- **Voice/audio** → transcribe via `voice_handler.py`
- **Text** → natural language queries

---

## 8. Hooks (11 lifecycle events)

| Hook | Event | Purpose |
|------|-------|---------|
| session_start.py | SessionStart | Inject project context, lessons, next steps |
| pre_tool_use.py | PreToolUse | PermissionAnalyzer, budget checks, OAuth protection |
| post_tool_use.py | PostToolUse | Auto-format Python with Black after Edit/Write |
| semgrep_scan.py | PostToolUse (Edit\|Write) | Security scanning (Semgrep 1.156.0) |
| user_prompt_submit.py | UserPromptSubmit | Inject active project context (max 200 tokens) |
| stop.py | Stop & SubagentStop | Close session in DB (duration + tokens), auto-commit, audit flag |
| subagent_start.py | SubagentStart | Record agent spawning in DB |
| postcompact.py | PostCompact | Post-compaction cleanup |
| precompact.py | PreCompact | Pre-compaction state preservation |
| permission_request.py | PermissionRequest | Handle permission escalations |
| post_tool_use_failure.py | PostToolUseFailure | Error logging and recovery |

---

## 9. MCP Servers

| Server | Command | Purpose |
|--------|---------|---------|
| filesystem | `npx @modelcontextprotocol/server-filesystem` | File operations |
| fetch | `python -m mcp_server_fetch` | HTTP fetch |
| github | `npx @modelcontextprotocol/server-github` | GitHub API |
| dqiii8-db | `python3 bin/tools/sqlite_mcp.py` | SQLite queries (read: `query`, write: `execute`) |
| context7 | `npx @upstash/context7-mcp` | Library documentation |

---

## 10. Skills (17 registered)

| Skill | Trigger | Auto-invoke |
|-------|---------|-------------|
| audit | `/audit` | Every 7+ days or 3+ session errors |
| quality-gate | `/quality-gate` | Post-refactoring |
| checkpoint | `/checkpoint` | Before risky changes |
| handover | `/handover` | After 50+ turns |
| mobilize | `/mobilize <goal>` | Complex multi-domain tasks |
| evolve | `/evolve` | Manual — consolidate instincts into skills |
| mode | `/mode analyst\|coder\|creative` | Manual |
| prompt-optimize | `/prompt-optimize` | Manual |
| skill-create | `/skill-create` | Manual |
| gemini-review | `/gemini-review` | Manual — Gemini Pro audit |
| weekly-review | `/weekly-review` | Manual |
| instinct-status | `/instinct-status` | Manual diagnostic |
| red-team | `/red-team` | Manual — adversarial testing |
| blue-team | `/blue-team` | Manual — defensive patching |
| security-cycle | `/security-cycle` | Manual — red→blue→verify |
| test-team | `/test-team` | Manual — agent coordination test |
| transcript-learn | `/transcript-learn` | Manual — YouTube/podcast → chunks |

---

## 11. My-Projects (6 projects)

### auto-report
**Status:** Active | **Stack:** Python, asyncio, Groq, SQLite, python-docx
**Purpose:** Automated DPI (internationalization potential) diagnosis via Telegram bot. 7-phase pipeline generates DOCX reports with scoring.
**DB:** `autoreporte.db` (documents, extracted_fields, generated_docx, company_rankings)

### automatic-nutrition
**Status:** MVP complete | **Stack:** Python, Pydantic v2, WeasyPrint, Groq
**Purpose:** B2B SaaS — personalized daily diets for nutritionists' clients. PDF delivery via Telegram/WhatsApp/email.
**Key:** BMR via Katch-McArdle, LLM diet generation with 3-retry, APScheduler (Sat 08:00 weekly plans, daily 07:30 sends)

### content-automation
**Status:** Production | **Stack:** Python, MoviePy, FFmpeg, OpenCV, ElevenLabs, HF SDXL
**Purpose:** Faceless video pipeline — YouTube Shorts/long-form. 8-stage CIP v2 pipeline.
**Channels:** echoes_of_the_past (epic), primordial_economics (finance), tao_and_thought (philosophy), football_chronicles (sports), sapiens_origins (science)

### hult-finance
**Status:** Exploration | **Purpose:** Financial course content processing, study guide generation from Coursera materials.

### math-image-generator
**Status:** Development | **Purpose:** Mathematical visualizations from text descriptions (LaTeX/SVG).

### sentiment-jobsearch
**Status:** Design approved, implementation pending | **Purpose:** AI job search with real-time sentiment analysis → JSON profile + coaching report.

---

## 12. Database Summary (79 tables)

### Core Ops
`sessions`, `agent_actions`, `error_log`, `agent_registry`

### Knowledge
`vector_chunks`, `vec_knowledge`, `chunk_health`, `chunk_key_facts`, `chunks_fts`, `facts`, `facts_fts`, `subdomain_centroids`

### Metrics
`skill_metrics`, `audit_reports`, `code_metrics`, `learning_metrics`, `spc_metrics`, `model_satisfaction`, `knowledge_usage`, `amplification_log`, `routing_feedback`

### Research
`research_items`, `research_cache`, `github_research`, `github_search_sessions`, `intelligence_items`, `harvest_log`

### Memory
`instincts`, `vault_memory`, `vault_memory_archive`, `session_memory`, `memory_links`, `episodes`

### Objectives & Tasks
`objectives`, `jal_objectives`, `jal_steps`, `jal_conversations`, `jal_scoring_snapshots`, `jal_error_patterns`, `jal_error_taxonomy`, `loop_objectives`, `loop_errors`

### Benchmark
`benchmark_gold_standards`, `benchmark_multimodel_results`, `knowledge_benchmark_results`

### Security & Audit
`security_findings`, `gemini_audits`, `audit_reports`, `permission_decisions`, `learned_approvals`

### Chat & Media
`chat_messages`, `chat_sessions`, `video_metrics`, `video_outputs`, `scene_scripts`

### Config & Sync
`platform_config`, `cc_rate_limit`, `resource_claims`, `sync_state`, `morning_report`, `channel_stats`

---

## 13. Security Posture

| Area | Score | Detail |
|------|-------|--------|
| Red-team | 95/100 | Last scan 2026-03-25 |
| AgentShield | ~85/100 | Prompt injection, tool misuse |
| SSH | Hardened | Key-only, fail2ban active |
| UFW | Locked | Port 22 only |
| Semgrep | Active | PostToolUse hook on every Edit/Write |
| Shannon agent | Active | Risk-scores all file modifications |
| Dashboard | Localhost-only | 127.0.0.1:8080, token auth for remote |
| Telegram | Rate-limited | 10 /cc per hour, CHAT_ID whitelist |

---

## 14. What was fixed this session (2026-03-28)

### Handover items
- [x] Removed nomic-embed-text + v2-moe from Ollama (~1.2GB freed)
- [x] Regenerated all 6 knowledge indexes with bge-m3 (1024d)
- [x] Fixed composite threshold 0.40→0.30 (NLP chunks no longer filtered)
- [x] Fixed amplifier Tier B overhead (2500 char budget)

### B4.5 + B10
- [x] NLP keywords added to domain_classifier.py + subdomain_classifier.py
- [x] Project-scoped retrieval: `project=""` param + 1.2x boost in enricher
- [x] `--project` arg in openrouter_wrapper.py with CWD auto-detection

### System Audit Fixes
- [x] **C1:** Anthropic provider added to PROVIDERS + `_stream_via_claude_cli()` fallback
- [x] **C2:** llm7 removed from fallback chain (0% success)
- [x] **C3:** `/loop` command → director.py (was missing orchestrator_loop.py)
- [x] **C4:** `/sandbox_run` → bin/tools/sandbox_tester.py (wrong path)
- [x] **H1:** Default model → groq/llama-3.3-70b (was step-3.5-flash, 28s avg)
- [x] sys.path fixes: reconcile_errors.py, director.py, benchmark_multimodel.py, knowledge_search.py, stop.py
- [x] Session tracking: stop.py now populates total_duration_ms + total_tokens
- [x] projects/ directory created
- [x] Dead test removed (test_orchestrator_loop.py)
- [x] 461 errors resolved in error_log (0 unresolved remaining)

### Test Results
- **113 passed, 0 failed, 0 compile errors** across all bin/ + hooks/

---

## 15. Next Steps

### Immediate (next session)
1. **ANTHROPIC_API_KEY** — Get API key to enable direct Anthropic calls (currently using claude CLI subprocess as workaround)
2. **Commit all fixes** — 11 files modified, ready for commit
3. **key_facts_generator** — Run `python3 bin/agents/key_facts_generator.py --all` to populate chunk_key_facts table (currently empty)
4. **Verify Tier A agents** — Test finance-specialist, auditor, orchestrator via `python3 bin/core/openrouter_wrapper.py --agent finance-specialist "calculate WACC for Tesla"`

### Short-term
5. **Graph relations** — Populate relations table for hybrid search graph signal (currently empty placeholder)
6. **Project knowledge ingest** — Run `python3 bin/tools/knowledge_harvester.py --ingest --project auto-report` for each project's docs
7. **Benchmark DQ pipeline** — Run `python3 bin/tools/benchmark_multimodel.py` to measure DQ uplift with new bge-m3 embeddings
8. **Ollama model audit** — qwen2.5:3b and llama3 are unused, consider removing to free 6.6GB

### Medium-term
9. **content-automation pipeline** — CIP v2 needs testing end-to-end
10. **automatic-nutrition MVP** — Deploy Telegram bot
11. **sentiment-jobsearch** — Begin implementation (design approved)
12. **Dashboard auth** — Add proper token-based auth for remote access

---

## 16. File Map

| Resource | Path |
|----------|------|
| Database | `database/dqiii8.db` |
| Schema | `database/schema_v2.sql` |
| Wrapper | `bin/core/openrouter_wrapper.py` |
| GitHub Models | `bin/core/github_models_wrapper.py` |
| Embeddings | `bin/core/embeddings.py` |
| DB helper | `bin/core/db.py` |
| Notify | `bin/core/notify.py` |
| Validate env | `bin/core/validate_env.py` |
| Domain classifier | `bin/agents/domain_classifier.py` |
| Subdomain classifier | `bin/agents/subdomain_classifier.py` |
| Hierarchical router | `bin/agents/hierarchical_router.py` |
| Agent selector | `bin/agents/domain_agent_selector.py` |
| Knowledge enricher | `bin/agents/knowledge_enricher.py` |
| Knowledge search | `bin/agents/knowledge_search.py` |
| Knowledge indexer | `bin/agents/knowledge_indexer.py` |
| Hybrid search | `bin/agents/hybrid_search.py` |
| Intent amplifier | `bin/agents/intent_amplifier.py` |
| Confidence gate | `bin/agents/confidence_gate.py` |
| Domain lens | `bin/agents/domain_lens.py` |
| Vector store | `bin/agents/vector_store.py` |
| Fact extractor | `bin/agents/fact_extractor.py` |
| Instinct evolver | `bin/agents/instinct_evolver.py` |
| Memory decay | `bin/agents/memory_decay.py` |
| Key facts generator | `bin/agents/key_facts_generator.py` |
| Harvester | `bin/tools/knowledge_harvester.py` |
| Benchmark | `bin/tools/benchmark_multimodel.py` |
| Director | `bin/director.py` |
| Telegram bot | `bin/ui/jarvis_bot.py` |
| Dashboard | `bin/ui/dashboard.py` |
| Agent definitions | `.claude/agents/*.md` (27 files) |
| Agent map | `config/domain_agent_map.json` |
| Knowledge indexes | `knowledge/{domain}/index.json` (5 domains) |
| Agent knowledge | `.claude/agents/finance-specialist/knowledge/index.json` |
| Hooks | `.claude/hooks/*.py` (11 files) |
| Skills | `.claude/skills/*/SKILL.md` (17 skills) |
| Sessions | `sessions/*.md` (gitignored) |
| Lessons | `tasks/lessons.md` |
| Rules | `.claude/rules/*.md` |

---

*Generated: 2026-03-28 00:30 UTC | Tests: 113/113 | Errors: 0 unresolved | Score: 92/100*
