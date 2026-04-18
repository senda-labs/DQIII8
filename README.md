<p align="center">
  <h1 align="center">DQIII8</h1>
  <p align="center">Autonomous Multi-Agent Orchestration Engine</p>
  <p align="center">
    <img alt="Tests" src="https://img.shields.io/badge/tests-38%20passed-brightgreen">
    <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue.svg">
    <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-blue">
    <img alt="Platform" src="https://img.shields.io/badge/platform-Ubuntu%2024.04-lightgrey">
    <img alt="Claude Code" src="https://img.shields.io/badge/Claude%20Code-v2.1-blueviolet">
  </p>
</p>

**DQIII8 is a production-grade autonomous AI orchestration engine running on an SSH-only VPS.** It routes every query through a multi-tier LLM pipeline, enriches prompts with domain-specific knowledge, and enforces permissions and lifecycle events through 12 hooks deeply integrated with Claude Code.

Core design principles:
- **Cost-first routing** — always pick the cheapest model that can handle the task (local → free cloud → paid)
- **Knowledge injection** — domain knowledge retrieved via hybrid search (vector + FTS5) before the model sees the prompt
- **Deterministic permissions** — every tool call is evaluated by `PermissionAnalyzer` (APPROVE / DENY / ESCALATE)
- **Telegram-first UI** — `@YourBotName` is the primary external trigger, backed by 23 commands

> **Disclaimer:** Running DQIII8 requires a populated SQLite schema (79 tables), configured API keys for the provider tiers you want active, and Ollama installed locally for Tier C. See [INSTALL.md](INSTALL.md) for the full setup procedure. The system is designed for Ubuntu 22.04/24.04 on an SSH-only VPS.

---

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                        Entry Points                            │
│   Telegram /cc   │   CLI `j cc`   │   Director   │  Dashboard │
└────────┬─────────────────┬──────────────┬──────────────┬──────┘
         │                 │              │              │
         ▼                 ▼              ▼              ▼
┌───────────────────────────────────────────────────────────────┐
│                   DQ Pipeline  (8 Steps)                       │
│                                                               │
│  [1] Domain Classifier  (keyword centroid → embedding fallback)│
│  [2] Subdomain Classifier                                      │
│  [3] Hierarchical Router  (softmax, multi-level)              │
│  [4] Agent Selector  (27 specialists, 5 knowledge domains)    │
│  [5] Knowledge Enricher  (hybrid: vector + FTS5 + graph)      │
│  [6] Confidence Gate  (should enrich? cost/quality decision)  │
│  [7] Intent Amplifier  (tier-specific prompt scaffolding)     │
│  [8] Stream Response  (provider call + fallback chain)        │
└───────────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────────┐
│              Tiered LLM Router                              │
│                                                            │
│  Tier C  │  Ollama (local)   │ qwen2.5-coder:7b  │  $0    │
│  Tier B  │  Groq (free)      │ llama-3.3-70b     │  $0    │
│  Tier B+ │  GitHub Models    │ deepseek/codestral │  $0   │
│  Tier A  │  Anthropic (paid) │ claude-sonnet-4-6  │ ~$0.03│
│  Tier S  │  Anthropic (paid) │ claude-opus-4-6    │ ~$0.20│
└────────────────────────────────────────────────────────────┘
```

---

## Core Features

### 1 · Dynamic SQLite State Engine (79 tables)

All operational state lives in `database/dqiii8.db` — a SQLite database with 79 tables covering:

- **`instincts`** — learned keyword → task-type mappings with confidence scores. The Director queries these first; if confidence > 0.7, the LLM classification step is skipped entirely, reducing latency and cost.
- **`agent_actions`** — audit log of every tool call, model invocation, and permission decision
- **`model_performance`** — per-model satisfaction scores, latency, and cost metrics used by the adaptive router
- **`session_events`** — session lifecycle tracking (start, stop, tool usage, errors)
- **`knowledge_chunks`** — vector embeddings (bge-m3, 1024d) for the 5 knowledge domains

Schema is fully idempotent (`database/schema_v2.sql`). No migrations needed for fresh installs.

### 2 · Tiered LLM Pipeline (C → B → A → S)

```python
# bin/core/openrouter_wrapper.py
AGENT_ROUTING = {
    # Tier C — local, $0
    "python-specialist":  ("ollama", "qwen2.5-coder:7b"),
    # Tier B — cloud free, $0
    "research-analyst":   ("groq",  "llama-3.3-70b-versatile"),
    # Tier A — paid, Sonnet
    "finance-specialist": ("anthropic", "claude-sonnet-4-6"),
    # Tier S — paid, Opus (reserved for orchestration)
    "orchestrator":       ("anthropic", "claude-opus-4-6"),
}
```

Every provider is declared with its `api_key_env` variable name — no hardcoded keys anywhere in source. A strict URL allowlist (`_ALLOWED_HOSTS`) prevents any call to non-declared endpoints.

### 3 · Auto-Routing with Context Injection

The `Director` (`bin/director.py`) implements three-stage routing:

1. **Instincts fast-path** — SQL `SELECT keyword, confidence FROM instincts` → if match ≥ 0.7, skip LLM
2. **LLM classification** — Tier B (Groq) classifies `task_type`, `complexity`, `recommended_tier`
3. **Keyword fallback** — static `KEYWORD_TASK_TYPE` dict as last resort

Once the task type is determined, the `KnowledgeEnricher` retrieves the top-k relevant chunks and the `IntentAmplifier` restructures the prompt with tier-appropriate scaffolding before the final model call.

### 4 · Lifecycle Hooks (12 hooks)

All hooks live in `.claude/hooks/` and execute at Claude Code lifecycle events:

| Hook | Event | What it does |
|---|---|---|
| `pre_tool_use.py` | Before every tool | PermissionAnalyzer v3: APPROVE / DENY / ESCALATE; dynamic rules injection (~200–800 tokens); output truncation |
| `session_start.py` | Session open | Injects project context, last 5 lessons, last audit result |
| `stop.py` | Session close | Auto-commit, lessons extraction, session metrics |
| `post_tool_use.py` | After every tool | Records tool usage, cost estimation to DB |
| `notification.py` | Async events | Routes alerts to Telegram |

**PermissionAnalyzer** evaluates tool calls against:
- Pattern blocklist (`CRITICAL_PATTERNS`, `HIGH_RISK_PATTERNS`)
- Path blocklist (`.env`, `CLAUDE.md`, `dqiii8.db`, `.ssh/`)
- Budget check (daily Tier A/S spend)
- Mode awareness (`supervised` vs `autonomous`)

**Dynamic rules injection** — `rules_dispatcher.py` loads only the rule files relevant to the current context (1–3 of 16 rule files, ~200–800 tokens) instead of loading all rules on every hook invocation.

### 5 · Telegram UI (`@YourBotName`)

The Telegram bot (`bin/ui/dqiii8_bot.py`) acts as the primary external trigger. Key commands:

| Command | Description |
|---|---|
| `/cc <prompt>` | Route through full DQ pipeline + Claude Code |
| `/loop [project] [cycles]` | Start autonomous orchestration loop |
| `/status [project]` | System or project status |
| `/audit` | Full system health audit |
| `/dq` | DQ pipeline metrics and model scores |
| `/score` | Model satisfaction scores |
| `/auth_status` | OAuth/API key status |

---

## Directory Structure

```
dqiii8/
├── bin/
│   ├── core/
│   │   ├── openrouter_wrapper.py   Multi-provider LLM router with fallback chain
│   │   ├── db.py                   SQLite connection pool + query helpers
│   │   ├── db_security.py          Credential scanner + env conflict detection
│   │   ├── auth_watchdog.py        OAuth token monitoring
│   │   └── embeddings.py           bge-m3 vector embed (Ollama)
│   ├── agents/
│   │   ├── domain_classifier.py    Keyword → embedding domain classification
│   │   ├── knowledge_enricher.py   Hybrid vector + FTS5 retrieval
│   │   ├── intent_amplifier.py     Tier-specific prompt restructuring
│   │   └── ...                     22 more pipeline agents
│   ├── ui/
│   │   └── dqiii8_bot.py           Telegram bot (23 commands, async)
│   ├── tools/
│   │   ├── auto_learner.py         Instinct learning from session history
│   │   ├── auto_researcher.py      Background knowledge harvesting
│   │   └── truncate_output.py      Large-output guardrail
│   ├── director.py                 Intent parser + task router (instincts + LLM)
│   ├── orchestrator.py             /cc and /auto Telegram command handler
│   └── j.sh                        CLI entry: j cc, j loop, j status
│
├── .claude/
│   ├── hooks/                      12 lifecycle hooks (never modify lightly)
│   │   ├── pre_tool_use.py         PermissionAnalyzer v3 + rules injection
│   │   ├── session_start.py        Context injection (project, lessons, audit)
│   │   └── stop.py                 Auto-commit + lessons + metrics
│   ├── agents/                     9 active specialist agent definitions
│   └── skills/                     17 slash commands (/audit, /handover, etc.)
│
├── database/
│   ├── schema_v2.sql               Idempotent schema (source of truth)
│   ├── schema.sql                  Legacy schema reference
│   └── [*.db files — gitignored]   Runtime databases (never committed)
│
├── knowledge/                      5 domain indexes (bge-m3 embeddings, 1024d)
│   ├── applied_sciences/
│   ├── formal_sciences/
│   ├── natural_sciences/
│   ├── social_sciences/
│   └── humanities_arts/
│
├── config/
│   ├── .env.example                Environment variable template
│   ├── domain_agent_map.json       Domain → agent routing table
│   └── intelligence_sources.json  Knowledge harvesting sources
│
└── tests/                          Test suite (38 passing)
```

---

## Quick Start

```bash
git clone https://github.com/senda-labs/DQIII8
cd DQIII8
bash install.sh
```

**Requirements:** Ubuntu 22.04/24.04 (or WSL2), Python 3.10+, 8 GB RAM, Ollama (for Tier C local models).

```bash
# 1. Configure API keys
cp config/.env.example .env
nano .env

# 2. Initialize the database
python3 -m database.apply_migrations

# 3. Index the knowledge base (one-time, ~10 min)
for d in applied_sciences formal_sciences natural_sciences social_sciences humanities_arts; do
    python3 bin/agents/knowledge_indexer.py --domain "$d"
done

# 4. Start the Telegram bot
systemctl enable --now dqiii8-bot

# 5. Verify
python3 -m pytest tests/test_smoke.py -q
```

---

## Environment Variables

Copy `config/.env.example` to `.env` at project root:

| Variable | Tier | Required | Description |
|---|---|---|---|
| `GROQ_API_KEY` | B | **Yes** (free) | [console.groq.com](https://console.groq.com) |
| `GITHUB_TOKEN` | B+ | Recommended (free) | GitHub Models access |
| `OPENROUTER_API_KEY` | B/A | Optional | Any model via OpenRouter |
| `ANTHROPIC_API_KEY` | A/S | Optional | Direct API (OAuth via Claude Max also supported) |
| `TELEGRAM_BOT_TOKEN` | UI | For Telegram UI | From @BotFather |
| `TELEGRAM_CHAT_ID` | UI | For Telegram UI | Your chat ID |
| `FIRECRAWL_API_KEY` | Tools | Optional | Web crawling |
| `EXA_API_KEY` | Tools | Optional | Semantic web search |

At minimum, add a `GROQ_API_KEY` (free) to enable Tier B. Tier C (Ollama) works with zero API keys.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

MIT — see [LICENSE](LICENSE).
