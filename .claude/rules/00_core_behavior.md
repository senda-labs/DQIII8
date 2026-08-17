# Core Behavior — DQIII8

## Zero-Complacency Protocol (non-negotiable)
- Validate the **real final artifact** (deployed service, API response, DOCX, DB row) — not just tests or logs.
- Attack the root cause. Never patch symptoms. Never silence errors without understanding them.
- If an error repeats: instrument a structural QA check that blocks delivery until resolved.
- Never declare success until the artifact is verified end-to-end.

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

## Cost-First Rule (absolute)
Always start at the cheapest tier that can handle the task (C → B → B+ → A → S).
NEVER use Tier A/S for tasks Tier B can handle. Full table: `.claude/rules/03_tiering_and_routing.md`

## INVARIANTE NIM — Prioridad absoluta antes de Sonnet/Opus (non-negotiable)
NVIDIA NIM (Tier B+) es $0, calidad comparable o superior a Sonnet 4.6 en la mayoría de tareas.
ANTES de escalar a Tier A (Sonnet) o S (Opus), es OBLIGATORIO intentar NIM primero.

Nota: estos nombres de agente (`software-specialist`, `research-analyst`, `web-specialist`, `python-specialist`, `opt-analyst`) refieren al backend `AGENT_ROUTING` (NIM Tier B+), NO a los ficheros homónimos en `.claude/agents/*.md` (que están hardcodeados a Groq/Ollama) — son dos sistemas distintos que comparten nombre (drift confirmado 2026-08-11).

> ⚠️ **NIM caído a nivel de cuenta (2026-08-16):** todo POST a `/v1/chat/completions`
> devuelve 403 "Authorization failed" en cualquier modelo (GET `/v1/models` sí funciona).
> No es un problema de modelo — es la key/entitlement de `NVIDIA_API_KEY`. Requiere
> acción del usuario en build.nvidia.com. El wrapper sigue haciendo fallback automático
> a Groq mientras tanto; no desconectar NIM de la cadena.

**Modelos NIM preferidos por tipo de tarea:**
| Tarea | Modelo NIM | Latencia | Agente dqiii8 |
|-------|-----------|----------|---------------|
| Planificación, análisis, arquitectura | `nvidia/llama-3.3-nemotron-super-49b-v1.5` | — | `software-specialist`, `research-analyst` |
| Código, web, pseudocódigo (1M ctx) | `deepseek-ai/deepseek-v4-flash-0731` | — | `web-specialist`, `python-specialist` |
| Optimización, razonamiento | `nvidia/llama-3.3-nemotron-super-49b-v1.5` | — | `opt-analyst` |

_(Ambos reemplazados 2026-08-16: `mistral-large-3-675b-instruct-2512` y `deepseek-v4-flash`
estaban EOL/410 desde 2026-07-23 y 2026-08-07 respectivamente; latencias sin re-sondear.)_

**Reglas de escalado:**
1. Tarea de planificación / análisis / redacción → `software-specialist` (NIM Mistral 675B) PRIMERO
2. Tarea de código / web / pseudocódigo → `web-specialist` (NIM DeepSeek V4 Flash) PRIMERO
3. Solo si NIM devuelve 429 persistente (≥3 reintentos con backoff) → escalar a Tier A (Sonnet)
4. Tier S (Opus) SOLO para revisión final de calidad adversarial, nunca para generación inicial
5. Workflows Claude Code (Agent tool) consumen tokens Anthropic — usar Bash + dqiii8 wrapper para NIM real

**Cómo llamar NIM correctamente:**
```bash
python3 /root/dqiii8/bin/core/openrouter_wrapper.py --agent <agente> --no-enrich "<prompt>"
```
NUNCA usar el Agent tool del Workflow para tareas que puede resolver NIM. El Agent tool es Sonnet por defecto.
