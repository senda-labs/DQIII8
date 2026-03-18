# DQIII8

**The AI system that gets better every time you use it.**

You give an order in natural language. DQIII8 understands it, amplifies it with specialized knowledge from domain-expert agents, and executes it — without you needing to know how to write prompts.

## Features

- **Free local models via Ollama** — Run AI coding, debugging, and git operations without spending a cent. Tier 1 handles 80%+ of daily tasks.
- **Optional paid models** — Escalate to cloud APIs (Groq free tier, OpenRouter, Claude) only when local models can't solve it. You control the cost.
- **Domain-expert agents** — Python specialist, git specialist, code reviewer, content automator, finance analyst, creative writer, and more. Each agent carries its own knowledge base.
- **Learns from every session** — Mistakes are logged, patterns are extracted, and the system improves. Lessons persist across sessions and inform future decisions.
- **Built-in security** — Pre-commit hooks validate every action. Secrets are never written to code. Destructive operations require confirmation.
- **Autonomous 24/7** — Deploy on a VPS and let it work while you sleep. Telegram bot for notifications and remote control.

## Quickstart

```bash
# 1. Clone and install
git clone https://github.com/YOUR_USER/dqiii8.git && cd dqiii8
chmod +x install.sh && ./install.sh

# 2. (Optional) Add API keys for cloud models
nano .env

# 3. Launch
source .venv/bin/activate && claude
```

That's it. Start giving orders in plain language.

## Architecture

```
user command
    │
    ▼
bin/openrouter_wrapper.py classify  ──→  tier=1|2|3
    │
    ├── Tier 1 (local)   → Ollama  qwen2.5-coder:7b   python, debug, git
    ├── Tier 2 (free)    → Groq    llama-3.3-70b       review, research
    └── Tier 3 (paid)    → Claude  sonnet-4-6          arch, finance, creative
              │
              ▼
       Agent dispatcher
              │
    ┌─────────┴──────────┐
    │                    │
 Subagent            Worktree
 (direct)            (isolated)
    │                    │
    └────────┬───────────┘
             │
        metrics.db  ←  hooks (pre/post/stop)
             │
        /audit (7-day cycle)
```

DQIII8 uses a 3-tier model routing system:

| Tier | Provider | Cost | Used for |
|------|----------|------|----------|
| 1 | Ollama (local) | Free | Python, refactoring, debugging, git ops |
| 2 | Groq / OpenRouter | Free | Code review, analysis, research, media |
| 3 | Claude API | Paid | Finance, creative, architecture, multi-agent |

The system always tries the cheapest tier first and only escalates when needed.

## Agents

| Agent | Trigger | Isolation |
|-------|---------|-----------|
| orchestrator | 3+ domains, multi-agent | worktree |
| python-specialist | traceback, .py, refactor, debug | — |
| git-specialist | commit, branch, PR, merge | — |
| code-reviewer | review, after feature | worktree |
| content-automator | video, TTS, pipeline | — |
| data-analyst | WACC, DCF, chart, Excel | — |
| creative-writer | chapter, scene, novel | — |
| auditor | /audit, metrics report | — |

## Self-Improvement Loop

1. Every session — hooks log actions to the metrics database
2. Corrections — appended to `tasks/lessons.md` as instincts
3. Every 7 days — `/audit` generates a health report and score
4. Instincts — extracted and used to improve future sessions

## Project Structure

```
dqiii8/
├── bin/                  # Core scripts — model routing, agents, automation
│   ├── j.sh              # Main entry point (flag-based CLI)
│   ├── openrouter_wrapper.py
│   ├── ollama_wrapper.py
│   └── ...
├── config/
│   └── .env.example      # Environment template
├── database/
│   ├── schema.sql        # DB schema
│   └── audit_reports/    # Health reports
├── .claude/
│   ├── agents/           # Agent definitions + knowledge bases
│   ├── hooks/            # Lifecycle hooks (pre/post/stop)
│   └── rules/            # Context-loaded rule files
├── tasks/                # Active tasks, lessons, results
└── skills-registry/      # Reusable skill patterns
```

## Requirements

- Ubuntu 22.04 or 24.04 (other Linux distros may work)
- Python 3.10+
- 8GB RAM minimum (for local Ollama models)
- ~5GB disk for qwen2.5-coder:7b model

## Configuration

Copy the environment template and fill in the keys you need:

```bash
cp config/.env.example .env
```

All API keys are optional. With zero configuration, Tier 1 (local Ollama) works out of the box for coding tasks.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
