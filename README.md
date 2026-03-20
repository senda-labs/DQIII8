<p align="center">
  <h1 align="center">DQIII8</h1>
  <p align="center"><strong>Multi-tier AI orchestrator with domain-aware routing.</strong></p>
  <p align="center">Works for you. Go outside and live.</p>
  <p align="center">
    <a href="#quick-start">Quick Start</a> •
    <a href="#architecture">Architecture</a> •
    <a href="#knowledge-domains">Knowledge</a> •
    <a href="#dashboard">Dashboard</a> •
    <a href="https://ko-fi.com/ikermartiins">Support</a>
  </p>
  <p align="center">
    <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue.svg">
    <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-blue">
    <img alt="Platform" src="https://img.shields.io/badge/platform-Linux%20%7C%20WSL2-lightgrey">
    <img alt="Works offline" src="https://img.shields.io/badge/Tier%20C-works%20offline-success">
    <img alt="No GPU" src="https://img.shields.io/badge/GPU-not%20required-green">
  </p>
</p>

---

DQIII8 is an AI orchestrator that routes tasks to the cheapest model capable of solving them. It classifies your prompt by domain, enriches it with expert knowledge, selects the optimal tier, executes, and learns from the result. 70% of tasks run on free models. You pay only when complexity demands it.

```bash
curl -fsSL https://raw.githubusercontent.com/senda-labs/DQIII8/main/install.sh | bash
dq "Create a business plan for a coffee shop in my city"
```

**Requirements:** Ubuntu 22.04+ (or WSL2 on Windows / macOS), Python 3.11+, 4 GB RAM minimum. No GPU needed. Works fully offline at Tier C.

---

## How It Works

```
User prompt
    ↓
Bilingual classifier (EN/ES) → Domain detection across 5 knowledge areas
    ↓
Knowledge enrichment → Inject expert context from domain-specific knowledge bases
    ↓
Tier router → Select cheapest capable model
    ↓
Execution → Result + error logging + pattern detection + auto-learning
```

**Tier architecture:**

| Tier | Provider | Cost | Routes to |
|------|----------|------|-----------|
| **C** | Ollama (local) | $0 | Code, debug, git, tests |
| **B** | Groq / OpenRouter | $0 | Research, docs, code review |
| **A** | Claude Sonnet 4.6 | ~$0.01–0.05 | Finance, creative, architecture |
| **S** | Claude Opus 4.6 | ~$0.15–0.50 | Multi-agent planning |
| **S+** | Claude Opus 4.6 | On demand | Full orchestration |

Lowest tier that solves the task. Always.

---

## Quick Start

### Linux / macOS

```bash
curl -fsSL https://raw.githubusercontent.com/senda-labs/DQIII8/main/install.sh | bash
```

### Windows (WSL2)

```powershell
wsl --install -d Ubuntu-24.04
# Restart, open Ubuntu, then:
curl -fsSL https://raw.githubusercontent.com/senda-labs/DQIII8/main/install.sh | bash
```

### Configuration

```bash
cp .env.example .env

# Tier C works with zero keys (Ollama local)
# Add keys for higher tiers:
GROQ_API_KEY=gsk_...           # Tier B — free at groq.com
ANTHROPIC_API_KEY=sk-ant-...   # Tier A/S/S+ — pay as you go
TELEGRAM_BOT_TOKEN=...         # Optional: push notifications
TELEGRAM_CHAT_ID=...           # Optional: remote control via Telegram
```

### Verify your installation

```bash
python3 bin/verify_install.py
```

Checks file permissions, no leaked secrets, network exposure, dependency safety, and hook integrity.

### First health check

```bash
dq --audit     # Health score (no LLM required, works offline)
dq --status    # Tier availability and usage
```

---

## What It Can Do

A few examples of how DQIII8 classifies and routes prompts — no prompt engineering required:

```bash
# Finance → Social Sciences → Tier A
dq "Calculate the 99% VaR of a portfolio with 5 correlated assets using Monte Carlo"

# Nutrition → Natural Sciences → Tier B
dq "Build a 2500 kcal meal plan for a 80 kg athlete, 40% protein, lactose-free"

# Public tenders → Social Sciences / Law → Tier A
dq "Draft a technical solvency section for a public tender under LCSP Ley 9/2017"

# Code review → Applied Sciences → Tier C
dq "Review this Python class for SOLID violations and suggest refactors"

# Creative writing → Humanities & Arts → Tier B
dq "Write chapter 3 of a sci-fi novel where the protagonist discovers the signal"
```

Each prompt is automatically enriched with domain-specific context (VaR methods, macro tables, SARA thresholds, ISSN standards, narrative frameworks) before hitting any model.

---

## Architecture

DQIII8 is built around five composable layers:

**1. Classification** — Bilingual classifier (EN/ES) with high precision. 13/13 accuracy on mixed-language test suite.

**2. Knowledge** — Expert-level knowledge bases across all domains. Content sourced from regulatory standards, academic research, and industry frameworks. Real equations, industry parameters, not generic summaries.

**3. Routing** — Intelligent router that activates the right agents for each task. Multi-domain tasks are handled by coordinating specialized agents.

**4. Execution** — 5-tier model cascade. Automatic escalation on failure. Cost tracking per task.

**5. Learning** — Self-auditing via Statistical Process Control. Error pattern detection. Automatic lesson extraction. ML-based tier recommendation trained on historical usage data.

**Tech stack:** Python, SQLite, Ollama, Groq, Claude API, Telegram. No Docker. No Kubernetes. No complexity tax.

---

## Knowledge Domains

Five centroids cover the full spectrum of human expertise:

| Centroid | Agents | Coverage |
|----------|--------|----------|
| **Formal Sciences** | Mathematics, Statistics, Logic, Algorithms | Proofs, probability, complexity theory |
| **Natural Sciences** | Physics, Chemistry, Biology, Nutrition | BMR/TDEE, macros, RDA, supplements, genetics |
| **Social Sciences** | Finance, Marketing, Business, Law, Economics | Basel IV VaR, Google Ads, LCSP tenders, DCF/WACC |
| **Humanities & Arts** | Literature, Philosophy, History, Creative Writing | Narrative structure, ethics, historiography |
| **Applied Sciences** | Software Eng, Web Dev, Data Eng, AI/ML, DevOps | React, TypeScript, C++20, Docker, system design |

Each domain has specialized agents with real equations and industry parameters.

The free tier includes the routing framework. Expert knowledge bases are part of premium.

---

## Dashboard

```bash
dq --dashboard                    # Local: http://localhost:8080
dq --dashboard --host 0.0.0.0     # Remote: http://your-ip:8080?token=TOKEN
```

Token is stored in `database/.dashboard_token`.

Real-time visualization of task classification, agent routing, and execution — all observable before any model is called.

---

## Self-Auditing

DQIII8 audits itself using Statistical Process Control — the same methodology used in manufacturing to detect quality drift. No LLM required, works fully offline.

| Component | Weight |
|-----------|--------|
| Action Success Rate | 30% |
| Error Resolution | 30% |
| Hook Integrity | 20% |
| Learning Rate | 10% |
| System Health | 10% |

**Current score: 99.8/100 HEALTHY**

```bash
dq --audit    # Run anytime, works offline, zero cost
```

The auditor writes a report to `database/audit_reports/` and registers the result in the metrics database for trend tracking. Statistical Process Control triggers automatically re-audit if success rate drops below 95%, errors accumulate, or 7 days pass without a check.

---

## Nightly Automation

A built-in maintenance script runs automatically each night (or on demand):

```bash
bash bin/nightly.sh > tasks/nightly-report.md 2>&1 &
```

It runs knowledge re-indexing, domain classifier calibration, the local health audit, and commits any changes. Review the next morning:

```bash
cat tasks/nightly-report.md
```

---

## Comparison

| | ChatGPT / Claude.ai | OpenClaw | DQIII8 |
|---|---|---|---|
| Setup | Sign up, pay monthly | Node.js 22+, gateway config | `curl \| bash` → 5 min |
| Cost | $20–200/month | API keys + config | 70% free, pay per task |
| Self-auditing | No | No | Yes (SPC, offline) |
| Auto-learning | No | No | Yes (error patterns) |
| Prompt skill needed | Yes | Yes | No (domain enrichment) |
| Multi-domain routing | No | No | Yes (5 domains, specialized agents per domain) |
| Bilingual | Depends on model | No | EN/ES native |
| Your data | Their cloud | Your machine | Your machine |

---

## Free vs Premium

| | Community (MIT) | Premium |
|---|---|---|
| Framework | Full routing, auditor, auto-learning | ✓ |
| Tiers | C + B | C + B + A + S + S+ |
| Knowledge | Structure + IDENTITY files | Deep domain expertise across all domains |
| Agents | Basic routing | Specialized agents per domain |
| Dashboard | ✓ | ✓ |
| Support | GitHub Issues | Priority |

---

## CLI Reference

| Command | Description |
|---------|-------------|
| `dq "prompt"` | Route and execute (default Tier 3) |
| `dq --model local "prompt"` | Force Tier C (Ollama) |
| `dq --model groq "prompt"` | Force Tier B (Groq) |
| `dq --audit` | Local health audit — no LLM, offline |
| `dq --status` | Tier availability, Ollama ps, tmux sessions |
| `dq --classify "prompt"` | Preview which tier/domain would handle it |
| `dq --dashboard` | Launch web UI at localhost:8080 |
| `dq --loop PROJECT [N] [TIER]` | OrchestratorLoop — autonomous N-cycle execution |
| `dq --harvest` | Fetch papers from arXiv + Semantic Scholar |
| `dq --help` | Full flag reference |

---

## Telemetry

Disabled by default. Enable with `DQIII8_TELEMETRY=true` in `.env`.

Preview what would be sent: `python3 bin/telemetry.py --collect`

See [PRIVACY.md](PRIVACY.md) for details.

---

## Current Status

| Metric | Value |
|--------|-------|
| Health score | 99.8/100 HEALTHY |
| Classifier accuracy | 13/13 (EN + ES) |
| Knowledge chunks | Growing |
| Specialized agents | Growing |
| Tests passing | 45+ |

---

## The Story

Built by two finance students in London with zero CS background using Claude Code. Tried OpenClaw — loved the idea, too complex for non-developers. Built something different: an AI that works for you so you can go outside and live.

The system classifies your intent, enriches your prompt with domain expertise, picks the cheapest model that can do the job, and audits itself every week. You don't have to think about any of it.

If two finance students can build a system that scores 99.8/100 on its own health audit, imagine what it can do for you.

---

## Support

⭐ **Star this repo** — helps others find it.
🐛 **[Report issues](https://github.com/senda-labs/DQIII8/issues)** — every bug makes the system better.
☕ **[Buy me a coffee](https://ko-fi.com/ikermartiins)** — supports development.

---

## License

MIT — use it, modify it, ship it.

---

<p align="center">
  Built by <a href="https://github.com/ikermartiinsv-eng">Iker</a> and Guillermo at <a href="https://github.com/senda-labs">Senda Labs</a> with Claude Code.<br>
  <em>The irony of building an AI orchestrator with AI is not lost on us.</em>
</p>
