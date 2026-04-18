---
paths:
  - "bin/core/openrouter_wrapper.py"
  - "bin/director.py"
  - "bin/agents/**"
  - "config/domain_agent_map.json"
---
# Tiering & Routing — DQIII8

## Tier Table (Cost-First — STRICT)

| Tier | Provider | Model | Cost | Default use |
|---|---|---|---|---|
| C | Ollama (local) | `qwen2.5-coder:7b` | $0 | Code, git, pipeline, applied_sciences |
| B | Groq | `llama-3.3-70b-versatile` | $0 | Research, analysis, writing, domain knowledge |
| B+ | GitHub Models | `deepseek-v3-0324` / `codestral-2501` | $0 | Code review, long-context, fallback |
| A | Anthropic | `claude-sonnet-4-6` | ~$0.03/turn | Finance, orchestration, architecture decisions |
| S | Anthropic | `claude-opus-4-6` | ~$0.20/turn | Multi-agent coordination, system design ONLY |

**RULE: Start at C. Escalate only when:**
1. Task type is explicitly mapped to a higher tier (see `AGENT_ROUTING` in `openrouter_wrapper.py`).
2. Lower tier returns an error or produces demonstrably inadequate output.
3. Domain is finance/trading/architecture AND complexity ≥ ARCHITECTURE level.

**NEVER skip tiers.** NEVER use A/S for a task B can handle.

## Director Routing Algorithm (3 stages, in order)

1. **Instincts fast-path** — `SELECT keyword, confidence FROM instincts WHERE confidence > 0.7`
   If match found → use `task_type` from DB row, skip LLM classification entirely.

2. **LLM classification** — Tier B (Groq) classifies `task_type`, `complexity`, `recommended_tier`.
   Prompt: `_ANALYSIS_PROMPT` in `bin/director.py`.

3. **Keyword fallback** — `KEYWORD_TASK_TYPE` dict in `bin/director.py`. Last resort.

## Task Complexity → Tier Mapping

| Complexity | Executor | Trigger |
|---|---|---|
| READ_ONLY | executor-lite (Haiku) | grep, ls, git log, read, count |
| SIMPLE_WRITE | executor-lite (Haiku) | pytest, git commit, single-file edit |
| CODE_GEN | PAL/Ollama → Sonnet fallback | create, implement, refactor |
| ARCHITECTURE | Sonnet | design, plan, multi-file, >500-char prompt |
| CRITICAL | Sonnet + Opus plan-gate | security, credentials, production, deploy |

**Goal:** Haiku handles ≥70% of operations. Reserve Sonnet for reasoning-heavy tasks.

## Adding / Changing Routing

- To add a new agent: add entry to `AGENT_ROUTING` in `openrouter_wrapper.py` AND to `config/domain_agent_map.json`.
- To change a tier assignment: update `AGENT_ROUTING`. Do NOT change `TASK_TIER_MAP` in `director.py` without also updating `KEYWORD_TASK_TYPE`.
- All provider URLs are allowlisted in `_ALLOWED_HOSTS`. New providers must be added there first.
- API keys are env vars only (`api_key_env` field in `PROVIDERS` dict). NEVER hardcode.

## Escalation to Opus (Plan Gate)

Escalate to Opus ONLY when in `DQIII8_MODE=autonomous` AND plan meets ≥1 criterion:
- Prompt < 15 words (vague), touches ≥5 files, architectural decision with multiple valid paths.
- Maximum 1 Opus escalation per task. Never re-escalate after Opus responds.
- Full gate logic: `.claude/rules_db/dqiii8-plan-gate.md`.
