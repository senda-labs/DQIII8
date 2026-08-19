<p align="center">
  <h1 align="center">DQIII8</h1>
  <p align="center">Autonomous, Cost-First Multi-Agent Orchestration Engine</p>
  <p align="center">
    <img alt="Tests" src="https://img.shields.io/badge/tests-1004%20passing-brightgreen">
    <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue.svg">
    <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-blue">
    <img alt="Platform" src="https://img.shields.io/badge/platform-Ubuntu%2022.04%2F24.04-lightgrey">
    <img alt="Claude Code" src="https://img.shields.io/badge/Claude%20Code-integrated-blueviolet">
  </p>
</p>

**DQIII8 is an autonomous AI orchestration engine built for SSH-only VPS deployment.**
Every request flows through a cost-first routing pipeline that always tries the cheapest
capable model first — local → free cloud → paid frontier — escalating only when the task
demands it. It is deeply integrated with [Claude Code](https://claude.com/claude-code)
through 15 lifecycle hooks, 22 skills, and 17 specialist agents.
(Counts are validator-enforced against the live tree — `check_readme_counts()` in
`bin/tools/validate_rules_registry.py`; `CLAUDE.md:16` is the canonical restatement.)

This repository is a **reference implementation**. It shows the architecture, routing
logic, hook system, and agent patterns so you can build a similar system with your own
models and providers. The knowledge base, databases, and credentials are populated
locally — see [Installation](#installation).

---

## Design principles

- **Cost-first routing** — pick the cheapest tier that can do the job; escalate only on explicit task-type match or tier failure. Never skip tiers.
- **Deterministic permissions** — every tool call is evaluated by `PermissionAnalyzer` (APPROVE / DENY / ESCALATE) inside a `pre_tool_use` hook before execution.
- **State in SQLite** — instincts, agent actions, routing feedback and permission decisions live in a local SQLite database. No external state store. (There is no `model_performance` or `session_events` table — see the SQLite section below.)
- **Knowledge injection (optional)** — domain knowledge retrieved via hybrid search (vector + FTS5) before the model sees the prompt. Off by default for a clean install.
- **Composable agents** — 17 specialist agents + 15 hooks + 22 skills form a layered permission and routing system, all configurable.

---

## Tier table

| Tier | Provider | Example model | Cost | When used |
|---|---|---|---|---|
| **C** | Ollama (local) | `qwen2.5-coder:7b` | $0 | Code, git, pipeline tasks |
| **B** | Groq | `llama-3.3-70b-versatile` | $0 | Research, analysis, writing |
| **B+** | NVIDIA NIM | `meta/llama-3.3-70b-instruct` | $0 · 40 RPM | Long-context (1M tokens), Groq 429 fallback |
| **B++** | GitHub Models | `deepseek-v3` / `codestral` | $0 | Code review, NIM fallback |
| **A** | Anthropic | `claude-sonnet-4-x` | ~$0.03/turn | Finance, orchestration, architecture decisions |
| **S** | Anthropic | `claude-opus-4-x` | ~$0.20/turn | Multi-agent coordination, system design only |

Fallback chain is **sequential** (not round-robin): `ollama → groq → nim → github`.

**Minimum viable install:** free `GROQ_API_KEY` only — Tier B fully active, $0.  
**Recommended free stack:** Groq + NVIDIA NIM + GitHub Models — Tiers B, B+, B++ at $0.

---

## Architecture

```
                         Entry points
    Telegram /cc  ·  CLI: dq cc / dq loop / dq status  ·  Director
                                  │
                                  ▼
                      DQ Pipeline  (7 steps)
  [1] Classify    domain + subdomain  (keyword centroid → embedding fallback)
  [2] Retrieve    hybrid knowledge search  (vector + FTS5)      [optional]
  [3] Gate        confidence check — is enrichment worth the cost?
  [4] Amplify     tier-specific prompt scaffolding
  [5] Route       cost-first tier selection with sequential fallback chain
  [6] Execute     provider call  (C → B → B+ → B++ → A → S)
  [7] Memory      record actions, cost, and satisfaction to SQLite
                                  │
                                  ▼
         Claude Code  ←──dispatch.py──→  NIM / Groq / GitHub workers
              │
    15 hooks · 22 skills · 17 agents · PermissionAnalyzer
```

---

## Core components

### Cost-first router — `bin/core/openrouter_wrapper.py`
Declares every provider with its `api_key_env` variable (no hardcoded keys) and a strict
`_ALLOWED_HOSTS` allowlist. `AGENT_ROUTING` maps each named agent to a `(provider, model)`
pair. HTTP errors (429 / 5xx) trigger automatic sequential fallback.

### Director (3-stage intent routing) — `bin/director.py`
1. **Instincts fast-path** — `SELECT keyword, confidence FROM instincts WHERE confidence > 0.7`; on a match, skip LLM classification.
2. **LLM classification** — Tier B (Groq) classifies `task_type`, `complexity`, `recommended_tier`.
3. **Keyword fallback** — static dict as last resort.

Optional: `DQIII8_USE_GRAPH=1` routes through a LangGraph `StateGraph` with identical output schema.

### Bidirectional bridge — `bin/core/dispatch.py`
Lets Claude Code dispatch tasks to NIM/Groq workers and collect results:
- `dispatch(agent, prompt)` — sync call, returns structured JSON
- `dispatch_parallel(tasks)` — fan-out to N agents, collect in order
- `DQIII8_USE_AGNO=1` — optional Agno AgentOS backend (NIM/Groq/GitHub agents with SQLite session memory)

### MetaGPT-pattern code quality — `bin/core/code_quality.py`
City-block decomposition pipeline:
1. **Optimization analysis** (NIM Mistral 675B) — review spec before writing
2. **Engineer** (NIM DeepSeek V4 Flash) — generate one self-contained function/class with contract docstring
3. **Sandbox** — execute generated code in an isolated subprocess
4. **Haiku Context Bombardment** — feed Haiku 4.5 all context, fire 100 adversarial questions (traceability, contracts, invariants, edge cases). Gaps = real quality debt.
5. **Opus reviewer** — invoked ONLY if `haiku_score < 70` or critical gaps found (cost gate keeps most runs at $0)

### Lifecycle hooks — `.claude/hooks/` (15 hooks)

| Hook | Lifecycle event | Responsibility |
|---|---|---|
| `pre_tool_use.py` | before every tool | PermissionAnalyzer (APPROVE / DENY / ESCALATE) + dynamic rule injection |
| `session_start.py` | session open | inject zone context, recent lessons, last audit |
| `post_tool_use.py` | after every tool | record cost estimate and tool usage to DB |
| `stop.py` | session close *and* subagent close | lessons extraction, session metrics, auto-commit of `tasks/lessons.md` + `projects/*.md`, and an **unconditional `git push origin master`**; plus an automatic handover note + commit + push for sessions ≥15 min (see `.claude/skills/handover/SKILL.md` §Two implementations) |

The table covers the hooks worth knowing first; the full set is whatever
`.claude/settings.json` wires — that file is the SSOT for which hook runs on which event.
`rules_dispatcher.py` and `semgrep_scan.py` live in `.claude/hooks/` but are **not** wired to
any lifecycle event: the first is a library imported by `pre_tool_use.py`, the second is
currently invoked by nothing.

`rules_dispatcher.py` injects a subset of the rule registry per tool call, never the whole
corpus. The canonical file and token ranges live in `rules_dispatcher.py`'s docstring and
`.claude/rules/02_hooks_and_permissions.md` — deliberately not restated here.

`PermissionAnalyzer` checks pattern blocklists, path blocklists, daily budget cap, and execution mode (`supervised` vs `autonomous`). A DENY is final — the wrapper never retries. The blocked- and governance-path lists are code constants in `.claude/hooks/permission_analyzer.py`, documented once in `.claude/rules/02_hooks_and_permissions.md`; no other doc, this one included, may restate them.

### SQLite state engine — `database/schema_v2.sql`
60 tables + 29 views. `schema_v2.sql` is the idempotent source of truth — apply it
for a fresh install; no migration scripts needed. Key tables: `instincts`, `agent_actions`,
`routing_feedback`. (`model_performance` and `session_events` were documented here previously
but do not exist in `schema_v2.sql` or the live DB — removed 2026-08-11 stress test.)

### Telegram UI — `bin/ui/dqiii8_bot.py`
Primary external trigger. Commands: `/cc`, `/loop`, `/status`, `/audit`, `/dq`, `/score`,
`/auth_status`, and more. Optional — the system works fully via CLI without it.

---

## Directory layout

```
dqiii8/
├── bin/                  Engine
│   ├── core/             openrouter_wrapper.py · dispatch.py · db.py
│   │                     code_quality.py · graph.py · agno_agents.py
│   ├── agents/           domain_classifier · knowledge_enricher · intent_amplifier …
│   ├── director.py       3-stage intent routing
│   └── orchestrator.py   /cc and /loop command handling
├── .claude/
│   ├── hooks/            15 lifecycle hooks
│   ├── skills/           22 slash-command skills
│   ├── agents/           17 specialist agent definitions
│   └── rules/            core behavior · tiering · database · hooks rules
├── config/               .env.example · domain_agent_map.json · claude_settings_template.json
├── database/             schema_v2.sql  (source of truth — *.db are gitignored)
├── knowledge/            README.md + AUDIT_REPORT.md stubs — populate locally
├── tests/                1004 tests across 43 files
├── examples/             usage examples
├── zones/                Obsidian-style architecture context for Claude Code
└── install.sh            one-shot installer
```

---

## Installation

**Requirements:** Ubuntu 22.04/24.04 (or WSL2), Python 3.10+.  
Ollama is optional (enables Tier C local models). The knowledge/RAG layer is also optional.

```bash
git clone https://github.com/senda-labs/DQIII8
cd DQIII8
bash install.sh
```

The installer:
1. Installs Python dependencies (hash-verified from `requirements.lock` if
   present, via `pip install --require-hashes`; falls back to unpinned
   `requirements.txt` otherwise). Regenerate the lock after editing
   `requirements.txt` with:
   `pip install pip-tools && pip-compile --generate-hashes --output-file=requirements.lock requirements.txt`
2. Prompts to install Ollama (optional — skip to start with Tier B only)
3. Pulls `qwen2.5-coder:7b` if Ollama is installed
4. Copies `config/.env.example` → `.env` if not present
5. Applies `database/schema_v2.sql` (creates all 60 tables)
6. Copies Claude Code settings template
7. Runs smoke tests

**Enable the optional knowledge base** (requires Ollama + `bge-m3`):
```bash
bash install.sh --with-knowledge
```
This additionally pulls `bge-m3`, indexes the 5 knowledge domains, seeds domain
classifier centroids, and migrates embeddings to `sqlite-vec`.

### Quick start

```bash
# 1. Add your API keys (Groq is the free minimum)
nano .env

# 2. Verify the install
python3 -m pytest tests/test_smoke.py -q

# 3. Route a task
dq cc "analyze Apple WACC"
dq status
```

---

## Environment variables

Copy `config/.env.example` to `.env`:

| Variable | Tier | Required | Source |
|---|---|---|---|
| `GROQ_API_KEY` | B | **Yes (free)** | [console.groq.com](https://console.groq.com) |
| `NVIDIA_API_KEY` | B+ | Recommended (free) | [integrate.api.nvidia.com](https://integrate.api.nvidia.com) |
| `GITHUB_TOKEN` | B++ | Optional (free) | GitHub → Settings → Developer settings |
| `ANTHROPIC_API_KEY` | A/S | Optional (paid) | [console.anthropic.com](https://console.anthropic.com) |
| `TELEGRAM_BOT_TOKEN` | UI | Optional | [@BotFather](https://t.me/BotFather) |
| `OLLAMA_BASE_URL` | C | Optional | default: `http://localhost:11434` |

Claude Code OAuth is also supported for Anthropic calls — set `ANTHROPIC_API_KEY=""`
in subprocess env to force OAuth instead of the direct API key.

---

## Documentation

| Document | Description |
|---|---|
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | Version history |
| [docs/DQIII8_PLUGIN_DESIGN.md](docs/DQIII8_PLUGIN_DESIGN.md) | DQIII8 as a Claude Code plugin |
| [docs/architecture_decision_context_efficiency.md](docs/architecture_decision_context_efficiency.md) | ADR-001: context efficiency |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution guidelines |
| [PRIVACY.md](PRIVACY.md) | Data handling |

---

## License

MIT — see [LICENSE](LICENSE).
