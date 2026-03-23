<p align="center">
  <h1 align="center">DQIII8</h1>
  <p align="center">
    <img alt="Tests" src="https://img.shields.io/badge/tests-91%20passing-brightgreen">
    <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue.svg">
    <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-blue">
    <img alt="Platform" src="https://img.shields.io/badge/platform-Ubuntu%2022.04%2B-lightgrey">
  </p>
</p>

**DQIII8 makes any AI model smarter by injecting domain knowledge and restructuring prompts before they reach the model.**

- Routes prompts to the cheapest model that can handle the task (local → free cloud → paid)
- Enriches prompts with relevant domain knowledge before the model sees them
- Adapts prompt structure per model tier (small models get more scaffolding, large ones get raw data)

---

## Quick Start

```bash
git clone https://github.com/senda-labs/DQIII8
cd DQIII8
bash install.sh
```

**Requirements:** Ubuntu 22.04/24.04 (or WSL2), Python 3.10+, 8 GB RAM. No GPU needed.

---

## How It Works

```
prompt → classify domain → retrieve knowledge → restructure prompt → route to model → response
```

| Tier | Provider | Cost | When |
|------|----------|------|------|
| C | Ollama (local) | $0 | Code, debug, git |
| B | Groq / Together AI (free) | $0 | Research, analysis, writing |
| A | Anthropic / OpenAI (paid) | ~$0.01–0.05 | Finance, architecture, multi-step |

The system always picks the cheapest tier that can handle the task.

---

## Supported Models

- **Ollama** (local, no API key): `qwen2.5-coder:7b`, any Ollama-compatible model
- **Groq** (free): `llama-3.3-70b-versatile`
- **Together AI** (free tier): `Llama-3.3-70B-Instruct-Turbo`
- **Anthropic**: `claude-sonnet-4-6`, `claude-opus-4-6`
- **OpenAI**: `gpt-4o`, `gpt-4o-mini`
- Any OpenAI-compatible endpoint via `OPENROUTER_API_KEY`

---

## Configuration

```bash
cp config/.env.example config/.env
# Edit config/.env and add your API keys
```

At minimum, add a `GROQ_API_KEY` (free at [console.groq.com](https://console.groq.com)) to enable Tier B.
Tier C (Ollama local) works with no keys at all.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

MIT — see [LICENSE](LICENSE).

---

<p align="center">
  Built by <a href="https://github.com/senda-labs">Senda Labs</a>
</p>
