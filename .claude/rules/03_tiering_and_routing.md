---
paths:
  - "bin/core/openrouter_wrapper.py"
  - "bin/director.py"
  - "bin/agents/**"
  - "config/domain_agent_map.json"
---
# Tiering & Routing — DQIII8

## Estado vigente: Anthropic-only (directiva usuario 2026-08-18)

Ninguna API no-Anthropic funciona hoy (NIM 403 desde 2026-08-16; Groq/Ollama/GitHub-free no
operativos hasta nueva verificación). Solo Sonnet (default) / Opus (revisión adversarial final).
La cadena multi-tier `C → B → B+ → B++ → A → S`, el catálogo NIM completo, el `FALLBACK_CHAIN`
de 7 claves y el checklist de reactivación están **archivados, no eliminados**, en
`.claude/rules_db/archive/multi-tier-dormant-2026-08.md`. Reactivación: probe manual 200 +
confirmación explícita del usuario levantando también la directiva Anthropic-only — ver
`.claude/rules/00_core_behavior.md` § REGLA NIM.

## Director Routing Algorithm (3 stages, in order)

_(Descripción del código en `bin/director.py`, independiente de qué tiers estén operativos.
Bajo Anthropic-only, el stage 2 apunta nominalmente a Groq — no operativo hoy — por lo que en
la práctica el routing efectivo cae al fallback de Sonnet.)_

1. **Instincts fast-path** — `SELECT keyword, confidence FROM instincts WHERE confidence > 0.7`.
   Nunca observado en producción (confianza máxima real: 0.68, por debajo del umbral) — código
   presente, no confirmado activo.

2. **LLM classification** — clasifica `task_type`, `complexity`, `recommended_tier`.
   Prompt: `_ANALYSIS_PROMPT` in `bin/director.py`.

3. **Keyword fallback** — `KEYWORD_TASK_TYPE` dict in `bin/director.py`. Last resort.

## Task Complexity → Executor Mapping

_(Eje distinto al de los tiers C/B/B+/B++/A/S: esta tabla mapea **clase de complejidad**
a **tipo de ejecutor**, no a tier de coste. No llamar "tiers" a estas clases.)_

| Complexity | Executor | Trigger |
|---|---|---|
| READ_ONLY | executor-lite / explorer-lite (CC interactive only) | grep, ls, git log, read, count |
| SIMPLE_WRITE | executor-lite (CC interactive only) | pytest, git commit, single-file edit |
| CODE_GEN | PAL/Ollama → Sonnet fallback | create, implement, refactor |
| ARCHITECTURE | Sonnet | design, plan, multi-file, >500-char prompt |
| CRITICAL | Sonnet + Opus plan-gate | security, credentials, production, deploy |

**Goal (dormant under Anthropic-only — no Haiku tier is currently routed anywhere in
`AGENT_ROUTING`; this goal predates the current directive and cannot be met today):**
Haiku handles ≥70% of operations. Reserve Sonnet for reasoning-heavy tasks.

> **Scope note — executor-lite / explorer-lite**: these are Claude Code native agents (`.claude/agents/`), invokable via the Agent tool in interactive CC sessions only. In `autonomous_loop.sh` (`claude -p` non-interactive mode) subagent spawning is unavailable — all routing goes through `AGENT_ROUTING` in `openrouter_wrapper.py`.

## Adding / Changing Routing

- To add a new agent: add entry to `AGENT_ROUTING` in `openrouter_wrapper.py` AND to `config/domain_agent_map.json`.
- To change a tier assignment: update `AGENT_ROUTING`. Do NOT change `TASK_TIER_MAP` in `director.py` without also updating `KEYWORD_TASK_TYPE`.
- All provider URLs are allowlisted in `_ALLOWED_HOSTS`. New providers must be added there first (automático al añadir a `PROVIDERS` dict).
- API keys are env vars only (`api_key_env` field in `PROVIDERS` dict). NEVER hardcode.
- `bin/core/providers/base.py` — Provider registry futuro (no activo). No usar hasta migración formal.

## Fallback Chain (SECUENCIAL, no round-robin) — dormant, full 7-key table archived

Free-tier fallback chains (`ollama`, `groq`, `nim`, `github`, `openrouter`, `pollinations`) are
non-operative under Anthropic-only. Full chain table + per-provider live-verification status →
`.claude/rules_db/archive/multi-tier-dormant-2026-08.md`.

El wrapper implementa retry con backoff exponencial (hasta 3 intentos por proveedor en
429/408/5xx/red, 1s→2s+jitter; errores auth/config 401/403/404 saltan al siguiente proveedor sin
reintentar) y un circuit breaker por proveedor persistido en `var/circuit_breaker.json`
(3 fallos consecutivos → abierto 120s → sonda half-open). Ver `_call_with_retry`, `_breaker_*`
en `openrouter_wrapper.py` + tests `tests/test_wrapper_routing_guards.py`.

`anthropic` no aparece en ningún valor de `FALLBACK_CHAIN`: si toda la cadena gratuita falla, el
wrapper sale con exit 1 en vez de escalar a Sonnet/Opus (decisión deliberada, cost-first). Los
agentes Tier A/S (`_NO_DOWNGRADE`) no degradan silenciosamente a Groq/Llama si el CLI de
`claude` falla: fallan alto con exit 2 (`DQIII8_ALLOW_DOWNGRADE=1` para permitir la degradación
explícitamente).

## Escalation to Opus (Plan Gate)

Escalate to Opus ONLY when in `DQIII8_MODE=autonomous` AND plan meets ≥1 criterion:
- Prompt < 15 words (vague), touches ≥5 files, architectural decision with multiple valid paths.
- Maximum 1 Opus escalation per task. Never re-escalate after Opus responds.
- Full gate logic: `.claude/rules_db/dqiii8-plan-gate.md`.
