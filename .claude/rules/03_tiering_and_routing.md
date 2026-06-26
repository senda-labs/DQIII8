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
| B+ | NVIDIA NIM | `meta/llama-3.3-70b-instruct` | $0 | Long-context (1M), dominio médico/fin, fallback groq 429 |
| B++ | GitHub Models | `deepseek-v3-0324` / `codestral-2501` | $0 | Code review, fallback NIM |
| A | Anthropic | `claude-sonnet-4-6` | ~$0.03/turn | Finance, orchestración, decisiones arquitectónicas |
| S | Anthropic | `claude-opus-4-8` | ~$0.20/turn | Multi-agent coordination, system design ONLY |

**NIM rate limits:** 40 RPM global (no headers x-ratelimit). Usa exponential backoff en 429. Modelos destacados disponibles: `deepseek-ai/deepseek-v4-flash` (1M ctx), `writer/palmyra-fin-70b-32k`, `writer/palmyra-med-70b-32k`, `meta/llama-4-maverick-17b-128e-instruct` (1M ctx). Modelo `nutrition-specialist` ya ruteado a NIM (`palmyra-med`).

**RULE: Start at C. Escalate only when:**
1. Task type is explicitly mapped to a higher tier (see `AGENT_ROUTING` in `openrouter_wrapper.py`).
2. Lower tier returns an error or produces demonstrably inadequate output.
3. Domain is finance/trading/architecture AND complexity ≥ ARCHITECTURE level.

**NEVER skip tiers.** NEVER use A/S for a task B can handle.

## Patrón: Pseudocódigo → Código → Validación

Pipeline de dos fases para implementación a partir de plan/spec:

```
[Plan / Pseudocódigo]
        ↓
  code-generator          NIM / deepseek-ai/deepseek-v4-flash   (B+, 1M ctx, 8s TTFB)
  python-specialist       NIM / deepseek-ai/deepseek-v4-flash   (B+)
  algo-specialist         NIM / deepseek-ai/deepseek-v4-flash   (B+)
  web-specialist          NIM / deepseek-ai/deepseek-v4-flash   (B+)
        ↓
  code-reviewer           Anthropic / claude-opus-4-8            (S — revisión estricta)
  code-validator          Anthropic / claude-opus-4-8            (S — alias explícito)
```

**Regla de uso:** Solo escalar a `code-reviewer`/`code-validator` cuando el código generado
toca ≥2 módulos, tiene lógica de negocio crítica, o el plan original tenía ambigüedad de spec.
Opus recibe: código generado + contexto completo del proyecto + spec original.
Opus ataca el código: busca bugs, violaciones de contratos, edge cases no cubiertos, deuda técnica.

**DeepSeek V4 Flash en NIM:** confirmado 200 OK, ~8s TTFB, 1M tokens contexto, $0.
Ventaja sobre Ollama qwen local: contexto de 1M (vs 32K), reasoning más profundo en pseudocódigo complejo.

## Director Routing Algorithm (3 stages, in order)

1. **Instincts fast-path** — `SELECT keyword, confidence FROM instincts WHERE confidence > 0.7`
   If match found → use `task_type` from DB row, skip LLM classification entirely.

2. **LLM classification** — Tier B (Groq) classifies `task_type`, `complexity`, `recommended_tier`.
   Prompt: `_ANALYSIS_PROMPT` in `bin/director.py`.

3. **Keyword fallback** — `KEYWORD_TASK_TYPE` dict in `bin/director.py`. Last resort.

## Task Complexity → Tier Mapping

| Complexity | Executor | Trigger |
|---|---|---|
| READ_ONLY | executor-lite / explorer-lite (CC interactive only) | grep, ls, git log, read, count |
| SIMPLE_WRITE | executor-lite (CC interactive only) | pytest, git commit, single-file edit |
| CODE_GEN | PAL/Ollama → Sonnet fallback | create, implement, refactor |
| ARCHITECTURE | Sonnet | design, plan, multi-file, >500-char prompt |
| CRITICAL | Sonnet + Opus plan-gate | security, credentials, production, deploy |

**Goal:** Haiku handles ≥70% of operations. Reserve Sonnet for reasoning-heavy tasks.

> **Scope note — executor-lite / explorer-lite**: these are Claude Code native agents (`.claude/agents/`), invokable via the Agent tool in interactive CC sessions only. In `autonomous_loop.sh` (`claude -p` non-interactive mode) subagent spawning is unavailable — all routing goes through `AGENT_ROUTING` in `openrouter_wrapper.py`.

## Adding / Changing Routing

- To add a new agent: add entry to `AGENT_ROUTING` in `openrouter_wrapper.py` AND to `config/domain_agent_map.json`.
- To change a tier assignment: update `AGENT_ROUTING`. Do NOT change `TASK_TIER_MAP` in `director.py` without also updating `KEYWORD_TASK_TYPE`.
- All provider URLs are allowlisted in `_ALLOWED_HOSTS`. New providers must be added there first (automático al añadir a `PROVIDERS` dict).
- API keys are env vars only (`api_key_env` field in `PROVIDERS` dict). NEVER hardcode.
- `bin/core/providers/base.py` — Provider registry futuro (no activo). No usar hasta migración formal.

## Fallback Chain (SECUENCIAL, no round-robin)

```
ollama  → groq → nim → openrouter → github → pollinations
groq    → nim → openrouter → github → pollinations
nim     → groq → openrouter → github → pollinations
github  → groq → nim → pollinations
```

Errores 429/500/502/503 en `stream_response()` triggean fallback automático al siguiente proveedor.

## Escalation to Opus (Plan Gate)

Escalate to Opus ONLY when in `DQIII8_MODE=autonomous` AND plan meets ≥1 criterion:
- Prompt < 15 words (vague), touches ≥5 files, architectural decision with multiple valid paths.
- Maximum 1 Opus escalation per task. Never re-escalate after Opus responds.
- Full gate logic: `.claude/rules_db/dqiii8-plan-gate.md`.
