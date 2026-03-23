# DQIII8 Architecture

> Single-file system map. Last updated: 2026-03-23.
> Verified against live files — not written from memory.

---

## 1. Pipeline DQ — flow of a prompt

```
user prompt
  │
  ├─► domain_classifier.py   classify_domain()        → domain label
  ├─► knowledge_enricher.py  get_relevant_chunks()    → top-k chunks (cosine sim)
  ├─► intent_amplifier.py    amplify()                → tier-specific prompt
  │     ├─ Tier C  _build_prompt_tier_c()  XML+CoT, 1 chunk max, 200 chars, <500 tok
  │     ├─ Tier B  _build_prompt_tier_b()  reference block, 3 chunks (has_specific_data)
  │     └─ Tier A  _build_prompt_tier_a()  data-only injection, 5 chunks
  └─► openrouter_wrapper.py  stream_response()        → model + log to DB
```

**Tier routing**

| Tier | Provider  | Model                   | When                               |
|------|-----------|-------------------------|------------------------------------|
| C    | Ollama    | qwen2.5-coder:7b        | code, refactor, debug, git         |
| B    | Groq      | llama-3.3-70b-versatile | review, analysis, research         |
| A    | Anthropic | claude-sonnet-4-6       | finance, architecture, orchestrate |

Classify: `python3 bin/core/openrouter_wrapper.py classify "<prompt>"`

---

## 2. File map — 40 scripts

### bin/ root (4)

| File                    | Purpose                                               |
|-------------------------|-------------------------------------------------------|
| `j.sh`                  | Main CLI entry point (`--model`, `--status`, `--classify`) |
| `director.py`           | Central pipeline orchestrator v3                      |
| `autonomous_loop.sh`    | Unattended VPS loop with Telegram reporting           |
| `nightly.sh`            | Nightly maintenance: DB vacuum, log rotation, report  |

### bin/core/ — infrastructure (9)

| File                  | Purpose                                                  |
|-----------------------|----------------------------------------------------------|
| `db.py`               | SQLite context manager (`get_db()`), query helpers       |
| `db_security.py`      | Input sanitization, SQL injection guards                 |
| `openrouter_wrapper.py` | Multi-provider routing (Groq/Anthropic), classify CLI  |
| `ollama_wrapper.py`   | Ollama local inference, agent system prompt loader       |
| `embeddings.py`       | Cosine similarity, nomic-embed-text via Ollama           |
| `notify.py`           | `send_telegram()` — all system notifications             |
| `rate_limiter.py`     | Per-key token bucket (Groq TPD guard)                    |
| `auth_watchdog.py`    | Claude Code OAuth health check (cron every 30 min)       |
| `validate_env.py`     | Startup env var validation, fails fast with clear errors |

### bin/agents/ — knowledge pipeline (9)

| File                    | Purpose                                                  |
|-------------------------|----------------------------------------------------------|
| `domain_classifier.py`  | Classifies prompt into one of 5 knowledge domains        |
| `knowledge_enricher.py` | Retrieves top-k chunks from domain index via embeddings  |
| `intent_amplifier.py`   | **Prompt Architect** — tier-specific template injection  |
| `domain_lens.py`        | Generates dynamic system prompts for domain specialists  |
| `hierarchical_router.py`| Multi-centroid weighted router (HMCWR) for chunk ranking |
| `knowledge_indexer.py`  | Chunks .md files + embeds → `index.json` per domain      |
| `knowledge_search.py`   | CLI search over index.json (cosine sim, top-k)           |
| `memory_decay.py`       | Ages and prunes `instincts` / `vault_memory` tables      |
| `template_loader.py`    | Loads and renders Jinja2-style agent prompt templates    |

### bin/monitoring/ — observability (5)

| File                    | Purpose                                                  |
|-------------------------|----------------------------------------------------------|
| `benchmark_knowledge.py`| Runs 120-eval DQ uplift benchmark (configs A–F)          |
| `auditor_local.py`      | Local health audit: DB stats, hook status, tier usage    |
| `analytics_collector.py`| Aggregates agent_actions → daily metrics tables          |
| `telemetry.py`          | Anonymous opt-in telemetry (disabled by default)         |
| `system_profile.py`     | Hardware detection, model recommendation on install      |

### bin/tools/ — utilities (10)

| File                    | Purpose                                                  |
|-------------------------|----------------------------------------------------------|
| `research_skill.py`     | Importable research/verify/update/measure API            |
| `paper_harvester.py`    | Fetches arXiv papers → adds to knowledge/ dirs           |
| `auto_researcher.py`    | Autonomous research loop using research_skill            |
| `auto_learner.py`       | Pattern-based lesson generator (no LLM, $0 cost)         |
| `lessons_consolidator.py`| Merges raw lessons → structured instincts in DB         |
| `github_researcher.py`  | GitHub topic search → `github_research` DB table         |
| `gemini_export.py`      | Exports module context for Gemini Pro external audit     |
| `gemini_review.py`      | Runs Gemini Pro code review via CLI                      |
| `sandbox_tester.py`     | Isolated test runner in `dqiii8-sandbox/` dir            |
| `voice_handler.py`      | STT via Groq Whisper + TTS via gTTS                      |

### bin/ui/ — interfaces (3)

| File                    | Purpose                                                  |
|-------------------------|----------------------------------------------------------|
| `jarvis_bot.py`         | Telegram bot — full mobile terminal (`/cc`, `/audit`)    |
| `dashboard.py`          | Web UI at localhost:8080 (metrics, logs, controls)       |
| `dashboard_security.py` | Session tokens, CSRF, login gate for dashboard           |

---

## 3. Database — dqiii8.db

**Core tables** (43 total in live DB)

| Table                       | Stores                                           |
|-----------------------------|--------------------------------------------------|
| `agent_actions`             | Every tool call: agent, duration, tokens, cost   |
| `sessions`                  | Claude Code session start/end, model used        |
| `instincts`                 | Auto-learned patterns with confidence scores     |
| `vault_memory`              | Persistent cross-session memory (with decay)     |
| `knowledge_benchmark_results`| Per-eval scores: accuracy, hallucinations, tokens|
| `audit_reports`             | Structured health reports from auditor           |
| `skill_metrics`             | Skill invocation counts and success rates        |
| `error_log`                 | Errors with session_id, agent, keyword tags      |
| `permission_decisions`      | Hook allow/deny decisions for pre_tool_use       |

**Analytical views** (19 total — 4 created by DQIII8, 15 pre-existing)

| View                   | Answers                                              |
|------------------------|------------------------------------------------------|
| `v_cost_savings`       | Daily actual cost vs. all-Sonnet equivalent (30d)    |
| `v_agent_performance`  | Success%, avg latency, failures by agent (7d)        |
| `v_tier_distribution`  | Daily action count and latency per tier (all time)   |
| `v_dq_uplift`          | Avg benchmark score by model × DQ × domain           |

---

## 4. Agents — .claude/agents/ (26 total)

**Core (8)** — full .md used as system prompt

| Agent               | Model              | Trigger                          |
|---------------------|--------------------|----------------------------------|
| `python-specialist` | qwen2.5-coder:7b   | Python code, tracebacks, refactor|
| `git-specialist`    | qwen2.5-coder:7b   | Commits, branches, PRs           |
| `code-reviewer`     | llama-3.3-70b      | Post-write code review           |
| `math-specialist`   | llama-3.3-70b      | Maths, stats, proofs             |
| `content-automator` | nemotron-nano-12b  | Video/content pipeline           |
| `finance-specialist`| claude-sonnet-4-6  | WACC, DCF, financial analysis    |
| `auditor`           | claude-sonnet-4-6  | `/audit`, system health          |
| `orchestrator`      | claude-sonnet-4-6  | `/mobilize`, multi-agent tasks   |

**Domain specialists (18)** — thin wrappers via `domain_lens.py`

`ai-ml`, `algo`, `biology`, `chemistry`, `data`, `economics`, `history`,
`language`, `legal`, `logic`, `marketing`, `nutrition`, `philosophy`,
`physics`, `software`, `stats`, `web`, `writing`

System prompt generated dynamically: domain_lens.py injects top-k
knowledge chunks relevant to the incoming query.

---

## 5. Knowledge — knowledge/

```
knowledge/
  formal_sciences/    28 docs →  92 chunks  (algorithms, math, stats)
  natural_sciences/   40 docs → 163 chunks  (biology, chemistry, physics)
  social_sciences/    67 docs → 324 chunks  (business, economics, finance, marketing)
  humanities_arts/     6 docs →  23 chunks  (history, language, philosophy)
  applied_sciences/   20 docs → 131 chunks  (software eng, web dev)
  ─────────────────────────────────────────
  TOTAL              161 docs → 733 chunks
```

Embedding model: `nomic-embed-text` (Ollama, 274 MB).  
Index format: `knowledge/{domain}/index.json` — list of `{text, embedding, source}`.  
Re-index: `python3 bin/agents/knowledge_indexer.py --domain {name}`

---

## 6. Services & Crons

| Service              | Entry point                       | Schedule               |
|----------------------|-----------------------------------|------------------------|
| Telegram bot         | `bin/ui/jarvis_bot.py`            | always-on (polling)    |
| Dashboard            | `bin/ui/dashboard.py`             | localhost:8080         |
| Auth watchdog        | `bin/core/auth_watchdog.py`       | every 30 min           |
| Nightly maintenance  | `bin/nightly.sh`                  | 03:00 UTC daily        |
| Morning report       | `bin/ui/jarvis_bot.py --morning-report` | 08:00 UTC daily  |
| Analytics collector  | `bin/monitoring/analytics_collector.py` | 09:00 UTC daily  |
| Memory decay         | `bin/agents/memory_decay.py`      | 04:00 UTC daily        |
| Sandbox tester       | `bin/tools/sandbox_tester.py`     | every 6 h              |
| Lessons consolidator | `bin/tools/lessons_consolidator.py` | 05:00 UTC monthly    |
| Auto researcher      | `bin/tools/auto_researcher.py`    | 06:00 UTC Mondays      |

**Telegram commands:** `/cc <prompt>`, `/cc_status`, `/auth_status`,
`/auth_test`, `/audit`, `/github_research`, `/gemini_export`  
Rate limit: 10 `/cc` per hour per chat_id.

---

## 7. Repos

```
senda-labs/DQIII8  (public, MIT)
  bin/         ← all 40 scripts
  knowledge/   ← 733 chunks, domain indexes
  .claude/     ← 26 agents, hooks, rules
  database/    ← schema_v2.sql only (no .db)
  install.sh   ← guided setup

dqiii8-workspace  (private, personal)
  config/.env          ← secrets
  database/dqiii8.db   ← live data (43 tables, 19 views)
  my-projects/         ← user projects
  overlay.sh           ← links workspace into public repo clone
```

`overlay.sh` creates symlinks: `my-projects/`, `config/.env`,
`.claude/settings.local.json`, `database/dqiii8.db`, `sessions/`, `tasks/`.
