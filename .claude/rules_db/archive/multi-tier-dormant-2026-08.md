---
paths: []
---
# Multi-tier free-provider chain — DORMANT (Anthropic-only directive, 2026-08-18)

**Not injected by `rules_dispatcher.py`** (no alias points here) — this is historical/reactivation
reference only, moved out of the hot path by Phase 2.2 of `docs/audits/2026-08-18-phase2-remediation-plan.md`.

## Why this is archived

The user directive of 2026-08-18: no non-Anthropic provider API works today (NIM confirmed
403 at the account level since 2026-08-16; Groq/Ollama/GitHub-free unverified but treated as
non-operative pending re-check). Only Claude/Anthropic models are usable going forward. The
multi-tier system below is **dormant, not deleted** — every fact here remains true of the code
and must be kept correct if the code changes, so a return to multi-tier operation can pick this
back up without re-deriving it.

Live, current-state summary (short form) lives in:
- `.claude/rules/00_core_behavior.md` § REGLA NIM (short paragraph, Anthropic-only)
- `CLAUDE.md:7` (one line)
- `.claude/rules/03_tiering_and_routing.md` (live stub, points here)

## Full tier chain (canonical, pre-outage)

`C (Ollama, local, $0) → B (Groq, $0) → B+ (NVIDIA NIM, $0, 40 RPM, 1M ctx) → B++ (GitHub Models, $0) → A (Anthropic Sonnet, ~$0.03/turn) → S (Anthropic Opus, ~$0.20/turn)`

| Tier | Provider | Model | Cost | Default use |
|---|---|---|---|---|
| C | Ollama (local) | `qwen2.5-coder:7b` | $0 | Code, git, pipeline, applied_sciences |
| B | Groq | `llama-3.3-70b-versatile` | $0 | Research, analysis, writing, domain knowledge |
| B+ | NVIDIA NIM | `nvidia/llama-3.3-nemotron-super-49b-v1.5` / `deepseek-ai/deepseek-v4-flash-0731` | $0 | Planificación/análisis/arquitectura; código/web/pseudocódigo (1M ctx) |
| B++ | GitHub Models | `deepseek-v3-0324` / `codestral-2501` | $0 | Retirado por GitHub (410) — fuera de la cadena de fallback desde 2026-08-16 |
| A | Anthropic | `claude-sonnet-5` | ~$0.03/turn | Solo si C y B fallan (o, con NIM sano, si NIM falla ≥3 veces). Orquestación, decisiones críticas |
| S | Anthropic | `claude-opus-5` | ~$0.20/turn | SOLO revisión adversarial final. Nunca generación inicial |

Rate limit NIM: 40 RPM global (compartido entre todos los modelos), sin headers `x-ratelimit` →
sin señal anticipada de throttle, exponential backoff en 429.

## NIM outage (current dormancy trigger)

**Confirmado en vivo 2026-08-16, reconfirmado 2026-08-16 contra 6+ modelos distintos:** todo
`POST /v1/chat/completions` devuelve 403 "Authorization failed" en cualquier modelo, incluidos
los ya reemplazados abajo. `GET /v1/models` sí funciona (key válida para listar), pero TODA
inferencia falla. No es un problema de modelo — la clave/entitlement de `NVIDIA_API_KEY` debe
revisarse/reemitirse en build.nvidia.com. Telemetría de producción: 0% de éxito sobre 86 llamadas.

### Criterio de reactivación (un agente NUNCA lo declara por su cuenta)

Dos condiciones necesarias, en este orden:
1. **Probe manual humano** contra el endpoint real del wrapper (`PROVIDERS["nim"]["base_url"]`
   = `https://integrate.api.nvidia.com/v1`, auth `Bearer $NVIDIA_API_KEY`) devuelve **200**:
   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" \
     -X POST https://integrate.api.nvidia.com/v1/chat/completions \
     -H "Authorization: Bearer $NVIDIA_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"model":"nvidia/llama-3.3-nemotron-super-49b-v1.5","messages":[{"role":"user","content":"ping"}],"max_tokens":1}'
   ```
   Un 200 en `GET /v1/models` **no cuenta**: ese endpoint funciona incluso durante el outage.
2. **El usuario confirma explícitamente la reactivación** (y, per the 2026-08-18 directive,
   also explicitly lifts the Anthropic-only constraint — the two are independent gates now).

Un agente NUNCA borra, relaja ni "considera resuelto" este flag por su cuenta, ni basándose
en un probe que él mismo haya ejecutado. Si un agente observa un 200, lo **reporta**; el
usuario aprueba la reactivación y actualiza `00_core_behavior.md` § REGLA NIM.

## Backend AGENT_ROUTING vs .claude/agents/*.md — namespace collision (drift confirmado 2026-08-11)

`software-specialist`, `research-analyst`, `web-specialist`, `python-specialist`, `opt-analyst`
as backend `AGENT_ROUTING` entries (NIM Tier B+) are NOT the same thing as the identically-named
files in `.claude/agents/*.md` (which are hardcoded to Groq/Ollama). Two distinct systems that
happen to share a name.

## NIM model catalog (nim-provider.md content, folded in wholesale, 2026-08-18)

### Qué es NIM en dqiii8
NVIDIA NIM es el Tier B+ del sistema de routing. API OpenAI-compatible en
`integrate.api.nvidia.com/v1`. Clave: `NVIDIA_API_KEY` en `.env`. Sondeo completo:
**50/121 modelos operativos** (2026-06-26). Fuente:
`docs/research/2026-06-26-nvidia-nim-investigation.md` (reconciliado 2026-08-11 — "52/121" era
drift de este fichero; el doc de investigación original y `03_tiering_and_routing.md` (live
stub, ver arriba) coinciden en 50/121).

### Rate limits y comportamiento
- **40 RPM global** — compartido entre TODOS los modelos. No es por modelo.
- **Sin headers x-ratelimit** en responses — no hay señal anticipada de throttle.
- **429** → triggea fallback automático en `stream_response()` → siguiente en `FALLBACK_CHAIN`.
- **Tier gratuito = dev/test/research ONLY**, no producción. Para autónomo en producción: Groq era primario (pre-Anthropic-only).
- Modelos pequeños (1B–8B) pueden tener latencia >300s — paradójico pero documentado.
- Modelos grandes MoE (Mistral 675B, Qwen 397B) responden más rápido que modelos pequeños.

### Modelos por categoría — solo los confirmados ✅ (catálogo 2026-08-16)

#### LLM general (routing síncrono)
| Modelo | Latencia | Cuándo usar |
|--------|----------|-------------|
| `nvidia/llama-3.3-nemotron-super-49b-v1.5` | — | **DEFAULT NIM** (actualizado 2026-08-16; el 675B anterior está EOL/410 desde 2026-07-23, latencia sin re-sondear) |
| `meta/llama-4-maverick-17b-128e-instruct` | 0.3s | Contexto largo (1M tokens) |
| `openai/gpt-oss-120b` | 0.5s | Alternativa calidad alta |
| `mistralai/mistral-small-4-119b-2603` | 0.2s | Balance velocidad/calidad |
| `mistralai/ministral-14b-instruct-2512` | 0.1s | Draft rápido, tarea simple |
| `nvidia/nemotron-mini-4b-instruct` | 0.1s | Tarea muy simple, máxima velocidad |

#### Código
| Modelo | Latencia | Cuándo usar |
|--------|----------|-------------|
| `deepseek-ai/deepseek-v4-flash-0731` | — | **Único código disponible** — 1M ctx, pseudocódigo→impl (actualizado 2026-08-16; slug anterior sin sufijo EOL/410 desde 2026-08-07) |

> ⚠️ Todos los modelos código especializados (Granite, CodeLlama, Codestral, StarCoder, CodeGemma) son **404**.

#### Safety / Moderation (todos <0.2s)
| Modelo | Uso |
|--------|-----|
| `nvidia/llama-3.1-nemoguard-8b-content-safety` | Gate de contenido general |
| `nvidia/llama-3.1-nemoguard-8b-topic-control` | Restricción temática |
| `meta/llama-guard-4-12b` | Content safety clasificación |
| `nvidia/gliner-pii` | Detección PII en texto |
| `nvidia/nemotron-content-safety-reasoning-4b` | Safety con razonamiento |
| `nvidia/llama-3.1-nemotron-safety-guard-8b-v3` | Safety avanzado |

#### Vision
| Modelo | Latencia | Capacidad |
|--------|----------|-----------|
| `microsoft/phi-4-multimodal-instruct` | 0.2s | Texto + imagen, tablas |
| `meta/llama-3.2-90b-vision-instruct` | 0.3s | Vision 90B, alta calidad |
| `nvidia/nemotron-nano-12b-v2-vl` | 0.3s | VLM Nemotron |
| `meta/llama-3.2-11b-vision-instruct` | 4.9s | Vision estándar |

#### Traducción
| Modelo | Latencia |
|--------|----------|
| `nvidia/riva-translate-4b-instruct-v1.1` | 0.2s |

#### Solo batch (>30s — NO usar en routing síncrono)
| Modelo | Latencia | Nota |
|--------|----------|------|
| `google/gemma-4-31b-it` | 37.8s | |
| `minimaxai/minimax-m2.7` | 38.9s | Reasoning — respuesta en `reasoning_content`, NO en `content` |
| `qwen/qwen3.5-397b-a17b` | 10.1s | 397B MoE — aceptable para batch |
| `qwen/qwen3.5-122b-a10b` | 170.1s | Solo offline |

### Embeddings — NO disponibles en hosted endpoint
Todos los modelos de embedding son 404 en `integrate.api.nvidia.com`.
Para RAG con NIM embeddings → deploy local vía Docker:
```bash
docker run --gpus all -p 8000:8000 \
  nvcr.io/nim/nvidia/nv-embedqa-e5-v5:latest
# Endpoint local: http://localhost:8000/v1
```
Benchmark: embed + reranker (`llama-nemotron-rerank-vl-1b-v2`) → +24% Recall@5 en RAG financiero.
Ver notebook: `NVIDIA/GenerativeAIExamples/RAG/notebooks/langchain/Chat_with_nvidia_financial_reports.ipynb`

### Añadir nuevo agente a NIM (para cuando se reactive)
```python
# En AGENT_ROUTING (openrouter_wrapper.py):
"nuevo-agente": ("nim", "nvidia/llama-3.3-nemotron-super-49b-v1.5"),

# SIEMPRE verificar que el modelo responde antes de commitear:
curl -s --max-time 30 -X POST https://integrate.api.nvidia.com/v1/chat/completions \
  -H "Authorization: Bearer $NVIDIA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"<model-id>","messages":[{"role":"user","content":"OK"}],"max_tokens":5}'
```

### Manejo de errores NIM
```python
# stream_response() ya maneja:
# 429 → fallback automático al siguiente proveedor en FALLBACK_CHAIN
# 500/502/503 → ídem
# Sin respuesta (timeout) → ídem tras curl --max-time

# Fallback chain desde NIM (catálogo 2026-08-16, ver openrouter_wrapper.py):
# nim → groq → pollinations
# (openrouter/github quitados como destino de fallback: 402 sin créditos / 404-410
# plataforma retirada — ambos confirmados muertos, sin reparación posible en código)
```

Referencia investigación completa: `docs/research/2026-06-26-nvidia-nim-investigation.md`

## Full FALLBACK_CHAIN (7 keys, complete — the live-stub table only ever showed 4)

```
ollama      → groq → nim → pollinations
groq        → nim → pollinations
nim         → groq → pollinations
github      → groq → nim → pollinations
openrouter  → groq → nim → pollinations   (openrouter entry itself: 402, no credits, removed as a fallback target 2026-08-16 but PROVIDERS entry kept intact)
pollinations → (terminal — no further fallback)
anthropic   → (never appears as a fallback target; see below)
```

`anthropic` never appears as a value in any `FALLBACK_CHAIN` entry: if the whole free chain
fails, the wrapper exits 1 rather than silently escalating to Sonnet/Opus (deliberate,
cost-first design). Conversely, Tier A/S agents (`_NO_DOWNGRADE`, derived from `AGENT_ROUTING`)
no longer silently downgrade to Groq/Llama if the `claude` CLI fails — they fail high with
exit 2 (`DQIII8_ALLOW_DOWNGRADE=1` to permit the downgrade explicitly).

**Realidad del código (remediación 2026-07-05):** el wrapper implementa retry con backoff
exponencial (hasta 3 intentos por proveedor en 429/408/5xx/red, 1s→2s+jitter; errores
auth/config 401/403/404 saltan al siguiente proveedor sin reintentar) y un circuit breaker por
proveedor persistido en `var/circuit_breaker.json` (3 fallos consecutivos → abierto 120s →
sonda half-open). Ver `_call_with_retry`, `_breaker_*` en `openrouter_wrapper.py` + tests
`tests/test_wrapper_routing_guards.py`.

## Estado real de openrouter / github / nim (verificado en vivo 2026-08-11, reconfirmado 2026-08-16)

- **openrouter**: el slug `qwen/qwen3-coder:free` está retirado (404); el slug correcto
  `qwen/qwen3-coder` (corregido en `_PROVIDER_DEFAULT_MODEL`) es de pago y la cuenta no tiene
  créditos (402 "Insufficient credits") → caído hasta que el usuario recargue créditos en
  openrouter.ai/settings/credits. Quitado como destino de `FALLBACK_CHAIN` 2026-08-16 (su
  `PROVIDERS`/modelo por defecto se dejan intactos para reactivación de una línea). El agente
  `hermes` (`AGENT_ROUTING`) apunta a `nousresearch/hermes-3-llama-3.1-405b:free` — mismo
  proveedor, mismo bloqueo, dormant junto con el resto de la cadena openrouter.
- **github**: ambos endpoints (`models.inference.ai.azure.com` deprecado y el sucesor
  `models.github.ai/inference`) responden 404/410 — GitHub retirando el servicio a nivel de
  plataforma (`github_models_retirement_brownout`). No reparable en código. Quitado como
  destino de `FALLBACK_CHAIN` 2026-08-16.
- **nim**: 403 "Authorization failed" en toda inferencia (`GET /v1/models` funciona). No es
  problema de modelo — la cuenta/key necesita revisión en build.nvidia.com. NIM se mantiene en
  `FALLBACK_CHAIN` (el 403 es fatal y salta al siguiente proveedor sin reintentos, coste ~1
  RTT), pero a nivel de decisión de routing NIM estaba saltado (pre-Anthropic-only): no elegir
  agentes NIM como primarios mientras dure el outage. Modelos EOL corregidos:
  `mistral-large-3-675b-instruct-2512` (410) → `nvidia/llama-3.3-nemotron-super-49b-v1.5`;
  `deepseek-v4-flash` (410) → `deepseek-ai/deepseek-v4-flash-0731`.
- Impacto real de openrouter/github: bajo, eran los últimos eslabones de sus cadenas. Impacto
  de NIM: alto — bloqueaba el tier B+ completo, degradando silenciosamente ~9 agentes a Groq
  (Tier B) desde al menos 2026-08-07 — ahora irrelevante bajo Anthropic-only.

## Pseudocódigo → Código → Validación pipeline (pre-Anthropic-only, dormant)

```
[Plan / Pseudocódigo]
        ↓
  code-generator          NIM / deepseek-ai/deepseek-v4-flash-0731   (B+, 1M ctx, 8s TTFB)
  python-specialist       NIM / deepseek-ai/deepseek-v4-flash-0731   (B+)
  algo-specialist         NIM / deepseek-ai/deepseek-v4-flash-0731   (B+)
  web-specialist          NIM / deepseek-ai/deepseek-v4-flash-0731   (B+)
        ↓
  code-reviewer           Anthropic / claude-opus-5            (S — revisión estricta)
  code-validator          Anthropic / claude-opus-5            (S — alias explícito)
```

Note (RC9 audit finding): `code-generator` does not exist as an agent anywhere in
`AGENT_ROUTING` or `.claude/agents/*.md` — this pipeline diagram is aspirational/ghost for that
one row; the other three (python-specialist, algo-specialist, web-specialist) are real.

## TIER_MAP / TIER_ORDER dead-code note

`TIER_MAP`/`TIER_ORDER` in the routing code were flagged during the 2026-08-17/18 audit as
possibly-unused given the static `AGENT_ROUTING` table does the real dispatch. Not resolved as
part of this archive fold — left as a TODO for whoever next touches `openrouter_wrapper.py`
under multi-tier reactivation: confirm live/dead via grep for callers, then either delete or
correctly document.

## Instincts fast-path caveat

`03_tiering_and_routing.md`'s Director Routing Algorithm step 1 ("Instincts fast-path" —
`SELECT keyword, confidence FROM instincts WHERE confidence > 0.7`) has never been observed to
fire in production telemetry: the max live confidence recorded is 0.68, below the 0.7
threshold. Keep the code path, but do not describe it as an active routing mechanism — it is
currently theoretical.

## Reactivation checklist (when the user lifts Anthropic-only AND NIM's account is confirmed healthy)

1. Human runs the manual probe above; confirms 200 on `POST /v1/chat/completions`.
2. User explicitly confirms both: (a) NIM account healthy, (b) Anthropic-only directive lifted.
3. Restore `00_core_behavior.md` § REGLA NIM and `03_tiering_and_routing.md`'s live content from
   this archive (or rewrite fresh if models/latencies have moved on — re-verify every model
   slug against `AGENT_ROUTING` before restoring, this file drifted twice in one day during the
   2026-08-17/18 audit cycle).
4. Re-run `validate_rules_registry.py`'s model-slug check across the full governance corpus —
   it now scans `.claude/rules_db/**`, `.claude/skills/**/SKILL.md`, and `CLAUDE.md` (Phase 2.1,
   2026-08-18), so any stale slug reintroduced during restoration will be caught before commit.
5. Undo the ~17 agent `.md` "dormant chain" Tier Routing notes back to their real NIM bindings
   (Phase 2.4 of the same remediation made these explicit precisely so this step is a grep-and-
   revert, not a re-derivation).

## Moved out of `03_tiering_and_routing.md` on 2026-08-18 (F10, panel-6 context economy)

Both blocks below were self-labelled dormant while still being injected on every `Agent`
call and every Bash matching `\bagent\b|\borchestrat`. Restore them via step 3 of the
reactivation checklist above.

### Task Complexity → Executor Mapping (dormant)

_(Eje distinto al de los tiers C/B/B+/B++/A/S: mapea **clase de complejidad** a **tipo de
ejecutor**, no a tier de coste. No llamar "tiers" a estas clases.)_

| Complexity | Executor | Trigger |
|---|---|---|
| READ_ONLY | executor-lite / explorer-lite (CC interactive only) | grep, ls, git log, read, count |
| SIMPLE_WRITE | executor-lite (CC interactive only) | pytest, git commit, single-file edit |
| CODE_GEN | PAL/Ollama → Sonnet fallback | create, implement, refactor |
| ARCHITECTURE | Sonnet | design, plan, multi-file, >500-char prompt |
| CRITICAL | Sonnet + Opus plan-gate | security, credentials, production, deploy |

**Goal (dormant):** Haiku handles ≥70% of operations, Sonnet reserved for reasoning-heavy
tasks. Under Anthropic-only `AGENT_ROUTING` routes exactly one agent to Haiku
(`context-probe`), so the goal predates the current directive and cannot be met.

> **Scope note — executor-lite / explorer-lite**: Claude Code native agents
> (`.claude/agents/`), invokable via the Agent tool in interactive CC sessions only. In
> `autonomous_loop.sh` (`claude -p` non-interactive) subagent spawning is unavailable — all
> routing goes through `AGENT_ROUTING` in `openrouter_wrapper.py`.

### Fallback chain notes (dormant)

Free-tier fallback chains (`ollama`, `groq`, `nim`, `github`, `openrouter`, `pollinations`)
are non-operative under Anthropic-only; the full per-provider table is above in this file.
`anthropic` appears in no `FALLBACK_CHAIN` value: if the whole free chain fails the wrapper
exits 1 instead of escalating to Sonnet/Opus (deliberate, cost-first).
