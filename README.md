# JARVIS — AI Orchestration System

> Multi-agent orchestration system built on Claude Code.
> Routes tasks between local models and Claude API based on cost and complexity.
> Self-improving via SQLite metrics + auditor agent.

## Architecture

```
j command
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
        jarvis_metrics.db  ←  hooks (pre/post/stop)
             │
        /audit (7-day cycle)
```

## Quick Start

**Prerequisites:** Python 3.11+, Node.js 18+, Claude Code

```bash
git clone https://github.com/ikermartiinsv-eng/jarvis
cd jarvis
cp .env.example .env   # fill your API keys
bash bin/j.sh          # launch
```

## Model Routing

| Task type | Tier | Provider | Model | Cost |
|-----------|------|----------|-------|------|
| Python, debug, refactor, git | 1 | Ollama (local) | qwen2.5-coder:7b | $0 |
| Code review, research, analysis | 2 | Groq | llama-3.3-70b-versatile | $0 |
| Video, TTS, subtitles | 2 | OpenRouter | nemotron:free | $0 |
| Finance, docs | 2 | OpenRouter | qwen3:free | $0 |
| Architecture, security, auth | 3 | Claude API | claude-sonnet-4-6 | Subscription |
| Financial analysis, WACC, DCF | 3 | Claude API | claude-sonnet-4-6 | Subscription |
| Creative writing, novel | 3 | Claude API | claude-sonnet-4-6 | Subscription |
| /mobilize, multi-agent | 3 | Claude API | claude-sonnet-4-6 | Subscription |

**Rule:** use the lowest tier that solves the task. Escalate only when lower tier fails.

```bash
python3 bin/openrouter_wrapper.py classify "refactor this function"
# → tier=1 provider=ollama model=qwen2.5-coder:7b
```

## Agents

| Agent | Trigger | Isolation |
|-------|---------|-----------|
| orchestrator | /mobilize, 3+ domains | worktree |
| python-specialist | traceback, .py, refactor, debug | — |
| git-specialist | commit, branch, PR, merge | — |
| code-reviewer | review, after feature | worktree |
| content-automator | video, TTS, ElevenLabs, pipeline | — |
| data-analyst | WACC, DCF, chart, Excel | — |
| creative-writer | chapter, scene, novel, xianxia | — |
| auditor | /audit, metrics report | — |

## Stack

Python · FastAPI · SQLite · Claude Code · OpenRouter · Groq · Ollama

## Project Structure

```
jarvis/
├── CLAUDE.md                    # System constitution (rules, routing, workflow)
├── bin/
│   ├── j.sh                     # Main entry point (flag-based CLI)
│   ├── openrouter_wrapper.py    # Tier-2 routing + classify command
│   ├── ollama_wrapper.py        # Tier-1 local model wrapper
│   └── gemini_review.py         # Background code review via Gemini
├── .claude/
│   ├── agents/                  # Agent definitions (8 specialized agents)
│   ├── hooks/                   # Lifecycle hooks: pre_tool_use, post_tool_use, stop
│   ├── rules/                   # Rule files loaded per context
│   └── commands/                # Slash command definitions (/audit, /mobilize...)
├── database/
│   ├── jarvis_metrics.db        # SQLite: sessions, actions, instincts, audits
│   ├── schema.sql               # DB schema
│   └── audit_reports/           # /audit output logs
├── projects/                    # Per-project state + next step
├── tasks/
│   ├── todo.md                  # Active tasks (orchestrator only)
│   ├── lessons.md               # Self-improvement log
│   └── results/                 # Agent output files
├── skills-registry/
│   ├── INDEX.md                 # Approved skills catalog
│   └── custom/                  # SKILL.md files for reusable patterns
└── sessions/                    # Session handover notes (auto-generated)
```

## Self-Improvement Loop

1. Every session → hooks log actions to `jarvis_metrics.db`
2. Corrections → appended to `tasks/lessons.md` as instincts
3. Every 7 days → `/audit` generates health report + score
4. Instincts → extracted to `instincts` table → used in future sessions

## Environment Variables

See `.env.example` for the full list of required variables.
