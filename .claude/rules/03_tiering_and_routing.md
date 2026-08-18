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

Bindings Anthropic vigentes en `AGENT_ROUTING` (`openrouter_wrapper.py`): `context-probe` →
`claude-haiku-4-5-20251001`; `code-reviewer`/`code-validator` → `claude-opus-5`;
`finance-specialist`/`auditor`/`orchestrator`/`tax-auditor`/`closing-specialist` →
`claude-sonnet-5`.

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

## Task Complexity → Executor Mapping — dormant

Tabla complejidad→ejecutor, goal Haiku ≥70% y scope note de executor-lite/explorer-lite:
dormantes bajo Anthropic-only, archivados en
`.claude/rules_db/archive/multi-tier-dormant-2026-08.md`.

## Adding / Changing Routing

- To add a new agent: add entry to `AGENT_ROUTING` in `openrouter_wrapper.py` AND to `config/domain_agent_map.json`.
- To change a tier assignment: update `AGENT_ROUTING`. Do NOT change `TASK_TIER_MAP` in `director.py` without also updating `KEYWORD_TASK_TYPE`.
- All provider URLs are allowlisted in `_ALLOWED_HOSTS`. New providers must be added there first (automático al añadir a `PROVIDERS` dict).
- API keys are env vars only (`api_key_env` field in `PROVIDERS` dict). NEVER hardcode.
- `bin/core/providers/base.py` — Provider registry futuro (no activo). No usar hasta migración formal.

## Fallback Chain — dormant (tabla completa archivada)

Las cadenas de fallback gratuitas no son operativas bajo Anthropic-only; tabla completa y
estado por proveedor → `.claude/rules_db/archive/multi-tier-dormant-2026-08.md`.

Sigue vigente en el wrapper: retry con backoff exponencial (hasta 3 intentos por proveedor en
429/408/5xx/red, 1s→2s+jitter; 401/403/404 saltan al siguiente sin reintentar) y circuit
breaker por proveedor en `var/circuit_breaker.json` (3 fallos → abierto 120s → sonda
half-open). Los agentes Tier A/S (`_NO_DOWNGRADE`) NO degradan en silencio si el CLI `claude`
falla: exit 2 (`DQIII8_ALLOW_DOWNGRADE=1` para permitirlo explícitamente). Ver
`_call_with_retry`, `_breaker_*` en `openrouter_wrapper.py` y
`tests/test_wrapper_routing_guards.py`.

## Escalation to Opus (Plan Gate)

Solo en `DQIII8_MODE=autonomous` y si el plan cumple ≥1: prompt <15 palabras, ≥5 ficheros, o
decisión arquitectónica con varias vías válidas. Máx. 1 escalación por tarea.
Regla canónica (límites duros y matices): `.claude/rules_db/dqiii8-plan-gate.md`.
