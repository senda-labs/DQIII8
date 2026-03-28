<p align="center">
  <h1 align="center">DQIII8</h1>
  <p align="center">
    <img alt="Tests" src="https://img.shields.io/badge/tests-38%20passed-brightgreen">
    <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue.svg">
    <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-blue">
    <img alt="Platform" src="https://img.shields.io/badge/platform-Ubuntu%2024.04-lightgrey">
    <img alt="Claude Code" src="https://img.shields.io/badge/Claude%20Code-v2.1-blueviolet">
  </p>
  <p align="center">
    <a href="https://ko-fi.com/ikermartiins"><img src="https://ko-fi.com/img/githubbutton_sm.svg" alt="Support on Ko-fi"></a>
  </p>
</p>

**DQIII8 makes any AI model smarter by injecting domain knowledge and restructuring prompts before they reach the model.**

- Routes prompts to the cheapest model that can handle the task (local → free cloud → paid)
- Enriches prompts with relevant domain knowledge before the model sees them
- Adapts prompt structure per model tier (small models get more scaffolding, large ones get raw data)
- Autonomous operation via Telegram bot with 23 commands
- 12 lifecycle hooks for Claude Code integration (auto-permissions, auto-commit, session tracking)
- 17 slash skills for auditing, handover, security testing, and more

---

## Quick Start

```bash
git clone https://github.com/senda-labs/DQIII8
cd DQIII8
bash install.sh
```

**Requirements:** Ubuntu 22.04/24.04 (or WSL2), Python 3.10+, 8 GB RAM. No GPU needed.

After installation:

```bash
# Configure your API keys
cp config/.env.example .env
nano .env

# Initialize the knowledge base
for d in applied_sciences formal_sciences natural_sciences social_sciences humanities_arts; do
    python3 bin/agents/knowledge_indexer.py --domain "$d"
done

# Start the bot
systemctl enable --now dqiii8-bot

# Verify
python3 -m pytest tests/test_smoke.py -q
```

---

## How It Works

```
prompt → classify domain → retrieve knowledge → restructure prompt → route to model → response
```

The 8-step DQ pipeline classifies your prompt's domain, retrieves relevant knowledge chunks via hybrid search (vector + FTS5), restructures the prompt with tier-appropriate scaffolding, and routes to the cheapest model that can handle the task.

| Tier | Provider | Cost | When |
|------|----------|------|------|
| C | Ollama (local) | $0 | Code, debug, git |
| B | Groq (free) | $0 | Research, analysis, writing |
| B+ | GitHub Models | $0 | Fallback, long-context code |
| A | Anthropic (paid) | ~$0.01–0.05 | Finance, architecture, orchestration |
| S | Anthropic (paid) | ~$0.15–0.50 | System design, multi-agent coordination |

The system always picks the cheapest tier that can handle the task.

---

## Supported Models

- **Ollama** (local, no API key): `qwen2.5-coder:7b`, `bge-m3` (embeddings), any Ollama-compatible model
- **Groq** (free): `llama-3.3-70b-versatile` — supports up to 9 API keys for round-robin rate limit management
- **GitHub Models** (free, requires `GITHUB_TOKEN`): `deepseek-v3`, `codestral-2501`, `gpt-4o-mini`
- **OpenRouter**: Any model via `OPENROUTER_API_KEY`
- **Anthropic**: `claude-sonnet-4-6`, `claude-opus-4-6` (via API key or Claude Code CLI OAuth)

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Entry Points                      │
│  Telegram /cc  │  CLI j cc  │  Director  │  Dashboard │
└───────┬─────────────┬───────────┬───────────┬────────┘
        │             │           │           │
        ▼             ▼           ▼           ▼
┌─────────────────────────────────────────────────────┐
│              DQ Pipeline (8 steps)                    │
│                                                       │
│  [1] Domain Classifier (keyword → embedding fallback) │
│  [2] Subdomain Classifier                             │
│  [3] Hierarchical Router (softmax, multi-level)       │
│  [4] Agent Selector (27 specialists, 5 domains)       │
│  [5] Knowledge Enricher (hybrid: vector+FTS5+graph)   │
│  [6] Confidence Gate (should enrich?)                 │
│  [7] Intent Amplifier (tier-specific prompt design)   │
│  [8] Stream Response (with fallback chain)            │
└─────────────────────────────────────────────────────┘
```

### Claude Code Integration

DQIII8 deeply integrates with Claude Code through:

- **12 lifecycle hooks** — auto-permissions, session tracking, security scanning, auto-commit
- **17 slash skills** — `/audit`, `/handover`, `/checkpoint`, `/mobilize`, `/red-team`, and more
- **PermissionAnalyzer v5** — intelligent APPROVE/DENY/ESCALATE for every tool use
- **Auto-commit on session close** — never lose work

---

## Configuration

```bash
cp config/.env.example .env
nano .env
```

| Variable | Source | Required |
|----------|--------|----------|
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) | **Yes** (free) |
| `GITHUB_TOKEN` | [github.com/settings/tokens](https://github.com/settings/tokens) | Recommended (free) |
| `OPENROUTER_API_KEY` | [openrouter.ai](https://openrouter.ai) | Optional |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) | Optional |
| `TELEGRAM_BOT_TOKEN` | [@BotFather](https://t.me/BotFather) | For Telegram UI |
| `TELEGRAM_CHAT_ID` | Your Telegram user ID | For Telegram UI |

At minimum, add a `GROQ_API_KEY` (free) to enable Tier B. Tier C (Ollama local) works with no keys at all.

---

## Telegram Bot Commands

<details>
<summary>View all 23 commands</summary>

| Command | Description |
|---------|-------------|
| `/cc <prompt>` | Execute via Claude Code (rate: 10/hr) |
| `/status [project]` | System or project status |
| `/loop [project] [cycles]` | Start autonomous loop |
| `/stop` | Stop autonomous loop |
| `/audit` | Full system health audit |
| `/dq` | DQ pipeline metrics |
| `/tasks` | List active tasks |
| `/task <id>` | Task detail |
| `/output <id>` | Task output |
| `/kill <id>` | Terminate task |
| `/score` | Model satisfaction scores |
| `/logs` | Recent errors |
| `/cc_status` | Claude Code status |
| `/auth_status` | OAuth status |
| `/auth_test` | Test authentication |
| `/auth_update` | Refresh OAuth |
| `/images [query]` | Generate images |
| `/research_status` | Research progress |
| `/integrar <id>` | Integrate research item |
| `/rechazar <id>` | Reject research item |
| `/voice on\|off` | Toggle TTS |
| `/sandbox_run` | Run sandbox tester |
| `/intl "COMPANY" URL` | Generate internationalization reports |

</details>

---

## Documentation

📖 **[Full System Guide](docs/dqiii8_guide.html)** — Complete reference with installation, commands, agents, hooks, pipeline details, and troubleshooting.

---

## Updating

```bash
cd /root/dqiii8
bash update_dqiii8.sh
```

Or manually:

```bash
git pull origin main
pip install --break-system-packages -U crawl4ai pdfplumber docxtpl
for d in applied_sciences formal_sciences natural_sciences social_sciences humanities_arts; do
    python3 bin/agents/knowledge_indexer.py --domain "$d"
done
systemctl restart dqiii8-bot
python3 -m pytest tests/test_smoke.py -q
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Support the Project

If DQIII8 is useful to you, consider supporting development:

<a href="https://ko-fi.com/ikermartiins"><img src="https://ko-fi.com/img/githubbutton_sm.svg" alt="Support on Ko-fi"></a>

---

## License

MIT — see [LICENSE](LICENSE).
