# DQIII8

**Works for you. Go outside and live.**

> The self-auditing AI orchestrator that routes 70% of your tasks to free models,
> learns from its own mistakes, and costs almost nothing.
> Built by a finance student with zero coding background using vibe coding.
> If I could build it, you can use it.

- ☕ **[Buy me a coffee](link)** — supports development

---

## What it does

You write a task in plain language. DQIII8 figures out which AI model can solve it
at the lowest cost, enriches your prompt with domain context, executes it,
and learns from the result.

| Tier | Cost | Models | Used for |
|------|------|--------|----------|
| **C** | $0 | Ollama (local) | Python, debug, git, tests |
| **B** | $0 | Groq, OpenRouter free | Code review, research, docs |
| **A** | ~$0.01-0.05/task | Claude Sonnet 4.6 | Finance, creative writing, architecture |
| **S** | ~$0.15-0.50/task | Claude Opus 4.6 | Multi-agent planning |
| **S+** | On demand | Claude Opus 4.6 | Full orchestration, critical tasks |

**Rule:** Lowest tier that solves the task. Always.

---

## Quick start

```bash
# Install (Ubuntu 22.04/24.04 — 5 minutes)
curl -fsSL https://raw.githubusercontent.com/senda-labs/DQIII8/main/install.sh | bash

# Your first task
dq "hello, who are you?"
```

**Requirements:** Ubuntu 22.04+, 4GB RAM minimum (8GB recommended), Python 3.11+.
No GPU needed. Works fully offline with Tier C.

---

## Why DQIII8?

| | ChatGPT / Claude | OpenClaw | DQIII8 |
|---|---|---|---|
| **Setup** | Sign up, pay monthly | Node.js 22+, gateway config | `curl \| bash` → 5 min |
| **Who it's for** | Everyone with $20/mo | Developers | Everyone |
| **Cost** | $20-200/month flat | API keys + config | 70% free, pay only when needed |
| **Self-auditing** | No | No | Yes — SPC health score |
| **Auto-learning** | No | No | Yes — detects error patterns |
| **Prompt skill needed** | Yes | Yes | No — domain enrichment handles it |
| **Your data** | Their cloud | Your machine | Your machine |

---

## How it works

1. You type: `dq "calculate the VaR of my portfolio at 95% confidence"`
2. **Classifier** detects domain → Social Sciences / Finance
3. **Knowledge enrichment** injects expert context (risk management frameworks, VaR methods)
4. **Router** sends to lowest capable tier → Tier A
5. Result delivered. Errors logged. Patterns detected. Lessons learned.

---

## Knowledge architecture

DQIII8 doesn't just route tasks — it thinks before acting.

Five knowledge domains cover the full spectrum of human expertise:

- **Formal Sciences** — Mathematics, logic, computation, statistics
- **Natural Sciences** — Physics, chemistry, biology
- **Social Sciences** — Economics, finance, law
- **Humanities & Arts** — Literature, philosophy, history
- **Applied Sciences** — Engineering, medicine, technology

The system enriches your prompt with relevant expert knowledge before sending it
to any model. You don't need to be an expert. The system is.

> The free tier includes the framework and basic routing.
> Expert knowledge bases and optimized domain configurations are part of premium tiers.

---

## Self-auditing

Most AI tools are black boxes. DQIII8 audits itself using Statistical Process Control —
the same methodology used in manufacturing to detect quality drift.

**Health score components:**
- Action success rate (30%)
- Error resolution (30%)
- Hook integrity (20%)
- Learning rate (10%)
- ADR compliance (10%)

During an external audit, the system was tested with 29 findings.
It verified each one with real data, accepted 12, proposed modifications to 10,
and rejected 7 with evidence — including catching that the auditor wrongly assumed
the database wasn't optimized and that there were zero tests.

**Current score: 91.1/100 HEALTHY** *(PROVISIONAL — 30 days needed for stable baseline)*

---

## The story

I'm a finance student in London. I don't have a CS degree.
I built DQIII8 over several weeks using Claude Code — vibe coding my way through
architecture decisions, agent design, and self-auditing systems.

I tried OpenClaw and loved the idea — a personal AI that works for you.
But it was too complex for people who aren't developers.

So I built something different. An AI that works for you
so you can go outside and live. It routes tasks to the cheapest model,
learns from errors, and tells you honestly how it's doing.

If a finance student can build a system that scores 91/100 on its own health audit,
imagine what it can do for you.

---

## What's free, what's premium

| | Community (free) | Premium (coming soon) |
|---|---|---|
| **Framework** | Full routing engine, auditor, auto-learning | ✓ |
| **Tiers** | C + B (local + free cloud) | C + B + A + S + S+ |
| **Agents** | Basic configs | Optimized expert agents |
| **Knowledge** | Structure + basic docs | Deep domain expertise, papers, frameworks |
| **Support** | GitHub Issues | Priority support |
| **Install** | Self-hosted | Self-hosted + managed (future) |

The framework is MIT licensed. Use it, modify it, ship it.
Expert configurations, optimized prompts, and premium knowledge bases
are what make the difference between a good response and an expert-level one.

---

## Configuration

Copy `.env.example` to `.env` and add your keys:

```bash
# Tier C works with zero keys (Ollama local)
GROQ_API_KEY=gsk_...          # Tier B — free at groq.com
ANTHROPIC_API_KEY=sk-ant-...  # Tier A/S/S+ — pay as you go
TELEGRAM_BOT_TOKEN=...        # Optional: notifications
TELEGRAM_CHAT_ID=...          # Optional: remote control
```

---

## Architecture

```
User prompt → Classifier (keyword + embedding) → Domain enrichment
    → Router (cheapest tier) → Agent execution → Result
    → Error logging → Auto-learning → Audit (every 7 days)
```

**10 specialized agents:** python-specialist, git-specialist, code-reviewer,
orchestrator, content-automator, data-analyst, creative-writer, auditor,
finance-analyst, quant-analyst.

**Tech stack:** Python, SQLite, Ollama, Groq, Claude API, Telegram.
No Docker required. No Kubernetes. No complexity tax.

---

## Current status

- Health score: **91.1/100** HEALTHY (provisional)
- 9/10 architectural blocks complete
- 32/32 tests passing
- 601 semantic memories active
- 5 domain knowledge centroids
- Auto-learning: active, detecting patterns

---

## Support the project

If DQIII8 saves you time or money:

- ⭐ **Star this repo** — it helps others find it
- 🐛 **Report issues** — every bug report makes the system better
- 💬 **Share feedback** — what would make this useful for you?

---

## License

MIT — the framework is free. Use it, modify it, ship it.

---

*Built by [Iker](https://github.com/ikermartiinsv-eng) at [senda-labs](https://github.com/senda-labs) with Claude Code.*
*The irony of building an AI orchestrator with AI is not lost on us.*
