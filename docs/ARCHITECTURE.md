# DQIII8 Architecture

> Last updated: 2026-03-24 — post Prompts 3–6 audit cycle.

## Pipeline Overview

Every prompt flows through 7 stages:

1. **Domain Classification** — keyword match with embedding fallback.
   Detects which of 5 knowledge domains the prompt belongs to
   (formal_sciences, natural_sciences, social_sciences, humanities_arts, applied_sciences).
   Script: `bin/agents/domain_classifier.py`

2. **Domain Specialist Selection** — keyword trigger matching.
   Selects the most relevant specialist agent within the domain
   and injects its system prompt. 0ms overhead — pure string matching,
   no LLM call. Word-boundary regex prevents substring false positives.
   Script: `bin/agents/domain_agent_selector.py`

3. **Knowledge Enrichment** — cosine similarity retrieval.
   Searches domain-specific knowledge chunks and injects the top 3
   most relevant into the prompt. A confidence gate skips enrichment
   when chunks add no signal (low score, Tier C agent, or generic query).
   Scripts: `bin/agents/knowledge_enricher.py`, `bin/agents/confidence_gate.py`

4. **Intent Amplification** — prompt restructuring per tier.
   Detects the intent (calculate, explain, compare, create, debug, review)
   and restructures the prompt with tier-appropriate scaffolding.
   Small models get more structure; large models get raw data.
   Script: `bin/agents/intent_amplifier.py`

5. **Tier Routing** — cheapest capable model.
   Tier C (Ollama local, $0) → Tier B (Groq free, $0) → Tier A (Anthropic, paid).
   Escalation rule: Tier C queries outside `applied_sciences` are automatically
   bumped to Tier B. Full fallback chain on provider failure.
   Script: `bin/core/openrouter_wrapper.py`

6. **Execution** — LLM call with enriched context.
   The model receives: specialist system prompt + knowledge chunks +
   restructured prompt + session memory (last 3 exchanges, Tier B/A only).

7. **Learning** — feedback loops.
   Results log to `routing_feedback` (per-tier accuracy tracking),
   `knowledge_usage` (chunk quality scoring), and `instincts` (pattern learning).
   A daily watchdog verifies system health. Weekly audit compares against
   baseline metrics and sends Telegram alerts on regressions.

---

## Data Flow Diagram

```
User prompt
│
▼
[1] Classify domain ──── keyword → embedding fallback
│
▼
[2] Select specialist ── trigger keywords → system prompt
│
▼
[3] Enrich knowledge ── confidence gate → cosine retrieval → top 3 chunks
│
▼
[4] Amplify intent ──── intent detection → tier-specific restructuring
│
▼
[5] Route to tier ───── C (local) → B (free cloud) → A (paid)
│
▼
[6] Execute ─────────── system prompt + chunks + prompt → LLM → response
│
▼
[7] Learn ───────────── routing_feedback + knowledge_usage + instincts
```

---

## Key Files

| Component | Script | Lines |
|-----------|--------|------:|
| Entry point | `bin/j.sh` | 360 |
| Router | `bin/core/openrouter_wrapper.py` | 986 |
| Classifier | `bin/agents/domain_classifier.py` | 735 |
| Specialist selector | `bin/agents/domain_agent_selector.py` | 88 |
| Knowledge enricher | `bin/agents/knowledge_enricher.py` | 255 |
| Confidence gate | `bin/agents/confidence_gate.py` | 64 |
| Intent amplifier | `bin/agents/intent_amplifier.py` | 828 |
| Working memory | `bin/agents/working_memory.py` | 121 |
| Auditor | `bin/monitoring/auditor_local.py` | 322 |
| Health watchdog | `bin/monitoring/health_watchdog.py` | 231 |

---

## Model Routing — 3 Tiers

| Tier | Provider | Model | Cost | When |
|------|----------|-------|------|------|
| C | Ollama (local) | `qwen2.5-coder:7b` | $0 | Code, refactor, debug, git |
| B | Groq | `llama-3.3-70b-versatile` | $0 | Review, analysis, research |
| A | Anthropic | `claude-sonnet-4-6` | ~$6/1M tokens | Finance, architecture, orchestration |

Current measured savings vs all-Sonnet baseline: **13–14% per month**
(1,215 of 9,141 queries deflected to Tier B/C over 30 days).

---

## Database

SQLite at `database/jarvis_metrics.db` — 47 tables.

**Core tables:**

| Table | Purpose | Rows (2026-03) |
|-------|---------|----------------|
| `agent_actions` | Every LLM call with tokens, tier, success | 11,050 |
| `sessions` | Session metadata and aggregates | 173 |
| `error_log` | Errors with resolution tracking | 156 |
| `instincts` | Learned patterns with confidence scores | 51 |
| `vault_memory` | Long-term memory with decay scoring | 717 |
| `routing_feedback` | Per-prompt tier routing decisions | 9,141 |
| `knowledge_usage` | Knowledge chunk quality tracking | live |
| `session_memory` | Recent exchange context (working memory) | live |

---

## Agents

27 agents defined in `.claude/agents/*.md`.

**Core agents** (always available via explicit `--agent` flag):

| Agent | Model | Purpose |
|-------|-------|---------|
| `python-specialist` | Tier C | Python, tracebacks, refactor |
| `git-specialist` | Tier C | Commits, branches, PRs |
| `web-specialist` | Tier C | HTML/CSS/JS, scraping |
| `finance-specialist` | Tier A | WACC, DCF, financial analysis |
| `code-reviewer` | OpenRouter free | Code review |
| `research-analyst` | Tier B | Research and synthesis |
| `orchestrator` | Tier A | Multi-agent coordination |
| `auditor` | Tier A | System health audit |

**Domain specialists** (18 agents, auto-selected by keyword in pipeline):

| Domain | Agents |
|--------|--------|
| formal_sciences | math, algo, stats |
| natural_sciences | biology, chemistry, physics, nutrition |
| social_sciences | finance, economics, marketing, legal |
| humanities_arts | writing, history, philosophy, language |
| applied_sciences | python, web, ai-ml, content-automator |

---

## Self-Monitoring

| Frequency | Script | What it checks |
|-----------|--------|----------------|
| Every 30 min | `bin/core/auth_watchdog.py` | Claude OAuth token validity |
| Daily 07:00 | `bin/monitoring/health_watchdog.py` | 8 system checks + Telegram alert |
| Daily 09:00 | `bin/monitoring/analytics_collector.py` | YouTube/content metrics |
| Weekly Mon | `bin/monitoring/weekly_audit.py` | SPC baseline + cost report |
| Weekly Mon | `bin/monitoring/routing_analyzer.py` | Per-tier latency + success rate |
| Monthly 1st | `bin/monitoring/knowledge_quality.py` | Chunk quality scoring |
| Monthly 1st | `bin/tools/lessons_consolidator.py` | Instinct consolidation |

Alert channel: Telegram bot (`bin/ui/jarvis_bot.py`, systemd service).

---

## Configuration

```
config/domain_agent_map.json   — 5 domains × N agents × trigger keywords
.claude/agents/*.md            — agent system prompts + model declarations
.claude/hooks/                 — 12 Claude Code lifecycle hooks
database/jarvis_metrics.db     — single SQLite file, all metrics
.env                           — API keys (not committed)
```

## CLI

```bash
dq "prompt"                    # route through full pipeline (default Tier A)
dq --model groq "prompt"       # force Tier B
dq --model local "prompt"      # force Tier C
dq --classify "prompt"         # show which tier would handle this
dq --status                    # project info, model, services
```

`dq` is installed at `/usr/local/bin/dq` and works from any directory.
