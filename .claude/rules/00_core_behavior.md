# Core Behavior — DQIII8

## Zero-Complacency Protocol (non-negotiable)
- Validate the **real final artifact** (deployed service, API response, DOCX, DB row) — not just tests or logs.
- Attack the root cause. Never patch symptoms. Never silence errors without understanding them.
- If an error repeats: instrument a structural QA check that blocks delivery until resolved.
- Never declare success until the artifact is verified end-to-end.

## Clarify Before Acting (non-negotiable)
- Prompt vague/short and doesn't fully pin down intent + scope + expected output quality → ASK first, don't guess-and-iterate.
- Skip only if the prompt already answers: (1) exact goal, (2) in/out scope, (3) enterprise-grade "done" bar.
- One sharp clarifying round beats multiple correction cycles.

## Autonomous Execution Rules
- Plans ≤5 steps, no destructive actions → execute autonomously, notify after.
- Plan touches ≥3 modules OR has ambiguous scope → enter plan mode first, wait for
  confirmation, then run `/panel-review <plan-file>` before implementation.
- Destructive / irreversible actions (rm -rf, DROP, force-push, schema change) → STOP, notify user, wait.
- Bug in production → fix immediately: read logs, isolate cause, resolve, verify. No hand-holding.

## Scope Discipline
- NEVER modify >3 files without a plan. Creep kills correctness.
- NEVER add features, abstractions, or error handling beyond what the task requires.
- NEVER write comments explaining WHAT code does — only WHY when non-obvious.

### Priority Ladder (Karpathy/Anthropic minimalism — every line is a liability)
Before writing code, stop at the first rung that resolves it: skip (YAGNI) → reuse
(grep first) → stdlib → installed dependency → one line → minimum new code. Doesn't
override validation/security/data-loss guards. `/panel-review` flags skipped rungs.

## Cost-First Rule (absolute)
Always start at the cheapest tier that can handle the task.
Cadena canónica: `C → B → B+ → A → S`; **cadena vigente hoy: `C → B → A`** (B+/NIM saltado,
ver § REGLA NIM abajo). NEVER use Tier A/S for tasks Tier B can handle.
Full table: `.claude/rules/03_tiering_and_routing.md`

## REGLA NIM — condicional al estado de la cuenta (non-negotiable)

**Estado actual: NIM EN OUTAGE (desde 2026-08-16). Tier B+ está FUERA de la cadena.**

> ⚠️ **NIM caído a nivel de cuenta (2026-08-16):** todo POST a `/v1/chat/completions`
> devuelve 403 "Authorization failed" en cualquier modelo (GET `/v1/models` sí funciona).
> No es un problema de modelo — es la key/entitlement de `NVIDIA_API_KEY`. Requiere
> acción del usuario en build.nvidia.com. Telemetría de producción: **0% de éxito
> sobre 86 llamadas**.

**Cadena de escalado MIENTRAS dure el outage (esta es la regla operativa, no una nota al pie):**
`C (Ollama) → B (Groq) → A (Sonnet)` — **saltando B+ (NIM) por completo.**
No intentar NIM "por si acaso": cada intento es un 403 garantizado que solo añade latencia.
Tier S (Opus) sigue reservado a revisión adversarial final, nunca a generación inicial.

**Cuando NIM esté sano (y SOLO entonces), la cadena vuelve a ser** `C → B → B+ → A → S`,
con B+ intentado antes de cualquier escalado a Tier A/S.

### Criterio de reactivación (un agente NUNCA lo declara por su cuenta)
Las dos condiciones son necesarias, en este orden:
1. **Probe manual humano** contra el endpoint real del wrapper
   (`PROVIDERS["nim"]["base_url"]` = `https://integrate.api.nvidia.com/v1`,
   auth `Bearer $NVIDIA_API_KEY`) devuelve **200**:
   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" \
     -X POST https://integrate.api.nvidia.com/v1/chat/completions \
     -H "Authorization: Bearer $NVIDIA_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"model":"nvidia/llama-3.3-nemotron-super-49b-v1.5","messages":[{"role":"user","content":"ping"}],"max_tokens":1}'
   ```
   Un 200 en `GET /v1/models` **no cuenta**: ese endpoint funciona incluso durante el outage.
2. **El usuario confirma explícitamente la reactivación.**

Un agente NUNCA borra, relaja ni "considera resuelto" este flag de outage por su cuenta,
ni basándose en un probe que él mismo haya ejecutado. Si un agente observa un 200,
lo **reporta**; la reactivación la aprueba el usuario y se refleja editando esta sección
y su gemela en `.claude/rules/03_tiering_and_routing.md`.

Nota: estos nombres de agente (`software-specialist`, `research-analyst`, `web-specialist`, `python-specialist`, `opt-analyst`) refieren al backend `AGENT_ROUTING` (NIM Tier B+), NO a los ficheros homónimos en `.claude/agents/*.md` (que están hardcodeados a Groq/Ollama) — son dos sistemas distintos que comparten nombre (drift confirmado 2026-08-11).

**Modelos NIM correctos (a usar cuando el outage se levante — el código debe mantenerlos
correctos con independencia del estado de la cuenta):**
| Tarea | Modelo NIM | Latencia | Agente dqiii8 |
|-------|-----------|----------|---------------|
| Planificación, análisis, arquitectura | `nvidia/llama-3.3-nemotron-super-49b-v1.5` | — | `software-specialist`, `research-analyst` |
| Código, web, pseudocódigo (1M ctx) | `deepseek-ai/deepseek-v4-flash-0731` | — | `web-specialist`, `python-specialist` |
| Optimización, razonamiento | `nvidia/llama-3.3-nemotron-super-49b-v1.5` | — | `opt-analyst` |

_(Ambos reemplazados 2026-08-16: `mistral-large-3-675b-instruct-2512` y `deepseek-v4-flash`
estaban EOL/410 desde 2026-07-23 y 2026-08-07 respectivamente; latencias sin re-sondear.)_

**Reglas de escalado — modo OUTAGE (vigente hoy):**
1. Tarea de código / git / pipeline → Tier C (Ollama) PRIMERO
2. Tarea de planificación / análisis / redacción / dominio → Tier B (Groq) PRIMERO
3. Solo si C y B fallan o son demostrablemente insuficientes → Tier A (Sonnet)
4. Tier S (Opus) SOLO para revisión final de calidad adversarial, nunca para generación inicial
5. Workflows Claude Code (Agent tool) consumen tokens Anthropic — usar Bash + dqiii8 wrapper
   para agotar antes los tiers gratuitos

**Reglas de escalado — modo SANO (solo tras reactivación aprobada por el usuario):**
se reinsertan los pasos NIM: planificación/análisis → `software-specialist` (NIM Nemotron
Super 49B) antes de Tier A; código/web → `web-specialist` (NIM DeepSeek V4 Flash 0731)
antes de Tier A; 429 persistente (≥3 reintentos con backoff) → escalar a Tier A.

**Cómo llamar a los tiers gratuitos correctamente:**
```bash
python3 /root/dqiii8/bin/core/openrouter_wrapper.py --agent <agente> --no-enrich "<prompt>"
```
NUNCA usar el Agent tool del Workflow para tareas que puede resolver un tier gratuito.
El Agent tool es Sonnet (Tier A) por defecto.
