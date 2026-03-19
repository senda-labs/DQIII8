---
name: dqiii8-multi-provider-routing
version: 1.0.0
source: git-analysis/dqiii8
analyzed_commits: 50
analyzed_date: 2026-03-12
repos: [$JARVIS_ROOT]
---

# DQIII8 Multi-Provider Routing

## Detected pattern

DQIII8 uses a 3-tier system with automatic fallback to route prompts
to the cheapest provider that can resolve the task.

**Evidence from history:**
- `feat: unified routing 3 tiers — Ollama+Groq+OpenRouter+Sonnet + j.sh Linux` (ba60bc7)
- `fix: CLAUDE.md Model Routing 3 tiers` (398cc6e, a407078) — 2 fixes in the same session
- `feat: OpenRouter wrapper + routing 4 levels` — prior iteration
- Files that always change together: `bin/openrouter_wrapper.py` + `CLAUDE.md`

## When to use this skill

- Add a new LLM provider to DQIII8
- Add a new agent and assign it a model
- Debug why a call is using the wrong tier
- Add fallback to an existing provider

## 3-tier architecture

```
Tier 1 — Local (free, no network latency)
  Provider: Ollama
  Model:    qwen2.5-coder:7b
  Use for:  Python, refactor, debug, git ops

Tier 2 — Free cloud (low latency, rate limits)
  Provider: Groq → llama-3.3-70b-versatile    (review, analysis)
  Provider: OpenRouter → qwen3:free             (research/documentation)
  Provider: OpenRouter → nemotron:free          (video/TTS/media)
  Fallback chain: OpenRouter → Groq → llm7.io → Pollinations

Tier 3 — Paid cloud (maximum capacity, no limits)
  Provider: Claude API → claude-sonnet-4-6
  Use for:  finance, creative writing, architecture, /mobilize
```

## Workflow: add a new provider

### 1. Add in `bin/openrouter_wrapper.py`

```python
PROVIDERS = {
    "new-provider": {
        "base_url": "https://api.new-provider.com/v1",
        "api_key_env": "NEW_PROVIDER_API_KEY",
        "headers_extra": {},
    },
    # ... existing providers
}
```

### 2. Add to AGENT_ROUTING if for a specific agent

```python
AGENT_ROUTING = {
    "my-agent": ("new-provider", "model-id"),
    # ...
}
```

### 3. Add to FALLBACK_CHAIN if it should be a fallback

```python
FALLBACK_CHAIN = {
    "openrouter": ["groq", "new-provider", "llm7", "pollinations"],
    # ...
}
FALLBACK_MODELS = {
    "new-provider": ("new-provider", "fallback-model"),
    # ...
}
```

### 4. Add API key to `.env`

```bash
NEW_PROVIDER_API_KEY=sk-...
```

### 5. Update CLAUDE.md § Model Routing

Add row to the table with: Condition | Tier | Provider | Model

### 6. Verify with classify

```bash
python3 bin/openrouter_wrapper.py classify "test prompt"
# Output: tier=N provider=X model=Y route=Z
```

## Files involved

| File | Role |
|------|------|
| `bin/openrouter_wrapper.py` | Core: PROVIDERS, AGENT_ROUTING, FALLBACK_CHAIN, stream_response() |
| `bin/ollama_wrapper.py` | Tier 1 local: Ollama calls |
| `bin/j.sh` | CLI entry point: flags --model local/groq/sonnet |
| `CLAUDE.md` | Documented routing table (always update together with wrapper) |
| `.env` | API keys: OPENROUTER_API_KEY, GROQ_API_KEY, ANTHROPIC_API_KEY |

## Detected anti-patterns (from fix: commits)

- **Not updating CLAUDE.md together with the wrapper** → `fix: CLAUDE.md Model Routing 3 tiers` (2 corrective commits)
- **Hardcoding ANTHROPIC_API_KEY** in Python code → use `os.getenv()` + `.env`
- **Calling claude CLI from inside Claude Code** → nested session error; use OpenRouter or subprocess with clean env
- **Not implementing fallback** → if provider fails without fallback, system fails silently

## Automatic classification

```python
# bin/openrouter_wrapper.py — classify subcommand
python3 bin/openrouter_wrapper.py classify "[prompt]"
# Returns: tier=N provider=X model=Y route=Z
```

Keywords tier-1: python, refactor, debug, test, git, commit, script, bug, fix
Keywords tier-2: review, analiz, research, evaluate, audit, explain
Keywords tier-3: wacc, dcf, finance, novel, architecture, mobilize
