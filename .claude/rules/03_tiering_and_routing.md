---
paths:
  - "bin/core/openrouter_wrapper.py"
  - "bin/director.py"
  - "bin/agents/**"
  - "config/domain_agent_map.json"
---
# Tiering & Routing — DQIII8

## ⚠️ REGLA NIM — condicional al estado de la cuenta (leer antes que cualquier otra regla)

**Estado actual: NIM EN OUTAGE. Cadena vigente `C → B → A` (Tier B+ SALTADO).**

> ⚠️ **NIM caído a nivel de cuenta desde 2026-08-16**: 403 "Authorization failed" en
> TODA inferencia (`GET /v1/models` funciona, `POST /v1/chat/completions` no, en
> cualquier modelo). Acción requerida del usuario en build.nvidia.com — no reparable
> en código. Telemetría: 0% de éxito sobre 86 llamadas. Ver comentario en
> `openrouter_wrapper.py` junto a `FALLBACK_CHAIN`.

Mientras dure el outage **no se intenta NIM antes de escalar**: Ollama (C) → Groq (B) →
Sonnet (A). Cuando la cuenta esté sana, y solo entonces, vuelve a ser obligatorio intentar
NIM (B+) antes de cualquier escalado a Tier A o S.

**Reactivación:** requiere (1) probe manual humano `POST /v1/chat/completions` con
`Bearer $NVIDIA_API_KEY` devolviendo 200 (un 200 en `GET /v1/models` NO vale) y
(2) confirmación explícita del usuario. Ningún agente puede levantar este flag por sí
mismo. Regla completa y comando de probe: `.claude/rules/00_core_behavior.md` § REGLA NIM.

Modelos NIM correctos (catálogo vigente 2026-08-16 — reemplazan los EOL de 2026-06-26;
el código debe mantenerlos correctos aunque la cuenta esté caída):
- **Planificación/análisis** → `nvidia/llama-3.3-nemotron-super-49b-v1.5` (agente: `software-specialist`)
- **Código/web (1M ctx)** → `deepseek-ai/deepseek-v4-flash-0731` (agente: `web-specialist`)

---

## Tier Table (Cost-First — STRICT)

| Tier | Provider | Model | Cost | Default use |
|---|---|---|---|---|
| C | Ollama (local) | `qwen2.5-coder:7b` | $0 | Code, git, pipeline, applied_sciences |
| B | Groq | `llama-3.3-70b-versatile` | $0 | Research, analysis, writing, domain knowledge |
| **B+** | **NVIDIA NIM** | `nemotron-super-49b` / `deepseek-v4-flash-0731` | **$0** | ⚠️ **EN OUTAGE — saltado. No intentar.** Cuando esté sano: prioridad sobre Sonnet en planificación, código y análisis |
| B++ | GitHub Models | `deepseek-v3-0324` / `codestral-2501` | $0 | ⚠️ Retirado por GitHub (410) — fuera de la cadena de fallback |
| A | Anthropic | `claude-sonnet-4-6` | ~$0.03/turn | Solo si C y B fallan (o, con NIM sano, si NIM falla ≥3 veces). Orquestación, decisiones críticas |
| S | Anthropic | `claude-opus-4-8` | ~$0.20/turn | SOLO revisión adversarial final. Nunca generación inicial |

**NIM — sondeo completo 2026-06-26 (50/121 activos), catálogo re-verificado 2026-08-16 (listado vía `/v1/models`, latencias no re-medidas — inferencia bloqueada por el 403 de cuenta):**

| Categoría | Modelos confirmados | Latencia |
|-----------|--------------------|---------:|
| LLM frontera | `nvidia/llama-3.3-nemotron-super-49b-v1.5` | sin re-medir |
| LLM 100B+ | `openai/gpt-oss-120b`, `nvidia/nemotron-3-super-120b-a12b` | 0.5–1.0s |
| Código (1M ctx) | `deepseek-ai/deepseek-v4-flash-0731` | sin re-medir |
| Safety | `nvidia/llama-3.1-nemoguard-8b-content-safety`, `meta/llama-guard-4-12b`, `nvidia/gliner-pii` | 0.1s |
| Visión | `microsoft/phi-4-multimodal-instruct`, `meta/llama-3.2-90b-vision-instruct` | 0.2–0.3s |
| Traducción | `nvidia/riva-translate-4b-instruct-v1.1` | 0.2s |
| Embeddings | **Todos 404** — usar alternativa externa | — |

Rate limit: 40 RPM global, sin headers x-ratelimit → exponential backoff en 429.
`writer/palmyra-*` y modelos código especializados (granite, codestral, starcoder) son 404 en esta cuenta.

**RULE: Start at C. Escalate only when:**
1. Task type is explicitly mapped to a higher tier (see `AGENT_ROUTING` in `openrouter_wrapper.py`).
2. Lower tier returns an error or produces demonstrably inadequate output.
3. Domain is finance/trading/architecture AND complexity ≥ ARCHITECTURE level.

**NEVER skip tiers** — con una única excepción vigente y documentada: **B+ (NIM) se salta
mientras dure el outage de cuenta** (ver arriba). NEVER use A/S for a task B can handle.

## Patrón: Pseudocódigo → Código → Validación

Pipeline de dos fases para implementación a partir de plan/spec:

```
[Plan / Pseudocódigo]
        ↓
  code-generator          NIM / deepseek-ai/deepseek-v4-flash-0731   (B+, 1M ctx, 8s TTFB)
  python-specialist       NIM / deepseek-ai/deepseek-v4-flash-0731   (B+)
  algo-specialist         NIM / deepseek-ai/deepseek-v4-flash-0731   (B+)
  web-specialist          NIM / deepseek-ai/deepseek-v4-flash-0731   (B+)
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
ollama  → groq → nim → pollinations
groq    → nim → pollinations
nim     → groq → pollinations
github  → groq → nim → pollinations
```

(`openrouter`/`github` quitados como destinos de fallback 2026-08-16 — ambos
confirmados muertos, ver nota más abajo; sus entradas en `PROVIDERS` quedan intactas
para reactivación de una línea si el usuario recarga créditos openrouter o GitHub
revierte la retirada de plataforma.)

Errores 429/500/502/503 en `stream_response()` triggean fallback automático al siguiente proveedor.

**Realidad del código (remediación 2026-07-05):** el wrapper ahora implementa
retry con backoff exponencial (hasta 3 intentos por proveedor en 429/408/5xx/red,
1s→2s+jitter; errores auth/config 401/403/404 saltan al siguiente proveedor sin
reintentar) y un circuit breaker por proveedor persistido en `var/circuit_breaker.json`
(3 fallos consecutivos → abierto 120s → sonda half-open). Ver `_call_with_retry`,
`_breaker_*` en `openrouter_wrapper.py` + tests `tests/test_wrapper_routing_guards.py`.

`anthropic` sigue sin aparecer en ningún valor de `FALLBACK_CHAIN`: si toda la cadena
gratuita falla, el wrapper sale con exit 1 — NO escala a Sonnet/Opus automáticamente
(decisión deliberada, cost-first). En sentido inverso, los agentes Tier A/S
(`_NO_DOWNGRADE`, derivado de `AGENT_ROUTING`) ya NO degradan silenciosamente a
Groq/Llama si el CLI de claude falla: fallan alto con exit 2
(`DQIII8_ALLOW_DOWNGRADE=1` para permitir la degradación explícitamente).
Detalle completo del proveedor NIM → `.claude/rules_db/nim-provider.md`.

**Estado real de `openrouter`, `github` y `nim` (verificado en vivo 2026-08-11, reconfirmado 2026-08-16):**
- `openrouter`: el slug `qwen/qwen3-coder:free` está retirado (404); el slug correcto
  `qwen/qwen3-coder` (ya corregido en `_PROVIDER_DEFAULT_MODEL`) es de pago y la cuenta
  no tiene créditos (402 "Insufficient credits") → openrouter caído hasta que
  el usuario recargue créditos en openrouter.ai/settings/credits. **2026-08-16: quitado
  como destino de `FALLBACK_CHAIN`** (su `PROVIDERS`/modelo por defecto se dejan intactos
  para reactivación de una línea).
- `github`: ambos endpoints (el deprecado `models.inference.ai.azure.com` y el sucesor
  `models.github.ai/inference`) responden 404/410 — GitHub está retirando el servicio
  a nivel de plataforma (`github_models_retirement_brownout`). No reparable en código.
  **2026-08-16: quitado como destino de `FALLBACK_CHAIN`** por el mismo motivo.
- `nim`: **hallazgo nuevo 2026-08-16** — toda inferencia (`POST /v1/chat/completions`)
  devuelve 403 "Authorization failed" en cualquier modelo probado (`GET /v1/models` sí
  funciona). No es un problema de modelo — la cuenta/key necesita revisión en
  build.nvidia.com. NIM se mantiene en `FALLBACK_CHAIN` (el 403 es fatal y salta al
  siguiente proveedor sin reintentos, coste ~1 RTT), pero **a nivel de decisión de
  routing NIM está saltado**: no elegir agentes NIM como primarios mientras dure el
  outage (ver § REGLA NIM arriba). Modelos EOL corregidos: `mistral-large-3-675b-instruct-2512` (410) →
  `nvidia/llama-3.3-nemotron-super-49b-v1.5`; `deepseek-v4-flash` (410) →
  `deepseek-ai/deepseek-v4-flash-0731`.
- Impacto real de openrouter/github: bajo, eran los últimos eslabones de sus cadenas.
  Impacto de NIM: alto — bloquea el tier B+ completo, degradando silenciosamente
  ~9 agentes a Groq (Tier B) desde al menos 2026-08-07.

## Escalation to Opus (Plan Gate)

Escalate to Opus ONLY when in `DQIII8_MODE=autonomous` AND plan meets ≥1 criterion:
- Prompt < 15 words (vague), touches ≥5 files, architectural decision with multiple valid paths.
- Maximum 1 Opus escalation per task. Never re-escalate after Opus responds.
- Full gate logic: `.claude/rules_db/dqiii8-plan-gate.md`.
