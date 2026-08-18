---
name: dispatch-agent
description: >
  Skill para despachar tareas a agentes NIM/Groq/GitHub desde esta sesión CC — DORMANTE
  bajo Anthropic-only (directiva usuario 2026-08-18), ver archivo al inicio del cuerpo.
  Habilita el Hermes Work Loop — CC orquesta, agentes B/B+ ejecutan (cuando reactivado).
---

# Dispatch Agent — Despachar tareas al routing system de dqiii8

**DORMANTE bajo Anthropic-only (directiva usuario 2026-08-18).** Este skill despacha a
NIM/Groq/Ollama — ninguno operativo hoy (NIM confirmado 403 desde 2026-08-16). No usar
`dispatch.py` para trabajo real mientras la directiva siga vigente; usa el Agent tool
nativo (Sonnet por defecto) o `claude -p` directo. El resto de este fichero describe la
mecánica completa para cuando se reactive — ver checklist de reactivación en
`.claude/rules_db/archive/multi-tier-dormant-2026-08.md`.

## Cuándo usar este skill (una vez reactivado el multi-tier)

Siempre que necesites ejecutar trabajo en NIM/Groq/Ollama en lugar de gastar tokens de Anthropic:

- Generar código desde pseudocódigo o spec → `python-specialist` o `algo-specialist`
- Investigación de dominio → `research-analyst`
- Múltiples subtareas paralelas independientes → `dispatch_parallel`
- Análisis de datos → `data-specialist`
- Safety check → `safety-checker`
- Revisión/validación de código → `code-reviewer` (Opus)

## Herramienta principal

```bash
cd /root/dqiii8

# Despacho único (sync, respuesta directa)
python3 bin/core/dispatch.py --agent <agente> --prompt "<tarea>"

# Con contexto de fichero
python3 bin/core/dispatch.py --agent python-specialist --context-file specs/impl.md --prompt "Implementa esto"

# Async (devuelve task_id, continúa en background)
python3 bin/core/dispatch.py --agent research-analyst --prompt "..." --async

# Leer resultado async
python3 bin/core/dispatch.py --read <task_id>

# Ver todos los agentes disponibles
python3 bin/core/dispatch.py --list-agents
```

## Hermes Work Loop — Patrón de orquestación

El Hermes Loop es el patrón estándar para trabajo multi-agente desde CC:

```
[CC: PLANIFICACIÓN]
       ↓
[dispatch_parallel → N agentes NIM/Groq]   ← Costo ~$0, 40 RPM NIM
       ↓
[CC: RECOLECTAR + FILTRAR resultados]
       ↓
[dispatch → code-reviewer (Opus)]          ← Solo si hay código crítico
       ↓
[CC: SINTETIZAR + ENTREGAR]
```

### Ejemplo: Implementar módulo desde pseudocódigo

```bash
# 1. Escribir tasks.json con las subtareas
cat > /tmp/tasks.json << 'EOF'
[
  {
    "agent": "python-specialist",
    "prompt": "Implementa la función parse_response() según este pseudocódigo: [...]",
    "context": "Módulo: bin/core/openrouter_wrapper.py. Usa solo stdlib + requests.",
    "timeout": 90
  },
  {
    "agent": "algo-specialist",
    "prompt": "Implementa el algoritmo de retry con exponential backoff para errores 429/503",
    "context": "Max 3 retries, base_delay=1s, max_delay=30s, jitter=True",
    "timeout": 60
  }
]
EOF

# 2. Despachar en paralelo (max_workers=6 por defecto)
python3 bin/core/dispatch.py --tasks /tmp/tasks.json | python3 -c "
import json, sys
results = json.load(sys.stdin)
for r in results:
    print(f\"[{r['agent']} → {r['provider']}/{r['model']}] {r['latency_ms']}ms\")
    print(r['response'][:500])
    print('---')
"

# 3. Si el código es crítico, escalar a Opus para revisión
python3 bin/core/dispatch.py \
  --agent code-reviewer \
  --context-file /tmp/generated_code.py \
  --prompt "Revisa este código buscando: bugs, edge cases, violaciones de contrato, deuda técnica"
```

### Ejemplo: Pipeline pseudocódigo → código → validación

```python
# Desde un script Python en dqiii8
from bin.core.dispatch import dispatch, dispatch_parallel

# Fase 1: Generación (NIM DeepSeek V4 Flash, 1M ctx, $0)
gen_result = dispatch(
    agent="python-specialist",
    prompt=pseudocode,
    context=project_context,
    timeout=90
)

# Fase 2: Revisión (Opus, solo si gen_result["status"] == "ok")
if gen_result["status"] == "ok":
    review = dispatch(
        agent="code-reviewer",
        prompt=gen_result["response"],
        context="Busca: seguridad, correctness, contratos violados",
        timeout=120
    )
```

## Tabla de agentes — cuándo usar cada uno (proveedores no-Anthropic dormantes hoy)

| Agente | Proveedor/Modelo | Usar para |
|--------|-----------------|-----------|
| `python-specialist` | NIM / deepseek-v4-flash | Implementación Python desde spec/pseudocódigo |
| `web-specialist` | NIM / deepseek-v4-flash | JS/TS/CSS, scraping, frontend |
| `algo-specialist` | NIM / deepseek-v4-flash | Algoritmos, estructuras de datos, optimización |
| `research-analyst` | NIM / mistral-large-675b | Investigación, síntesis, análisis contextual |
| `software-specialist` | NIM / mistral-large-675b | Arquitectura, diseño de sistemas |
| `data-specialist` | NIM / mistral-large-675b | SQL, DataFrames, análisis numérico |
| `ai-ml-specialist` | NIM / mistral-large-675b | ML, modelos, fine-tuning, métricas |
| `vision-specialist` | NIM / phi-4-multimodal | Análisis imagen/PDF/tabla |
| `safety-checker` | NIM / nemoguard-8b | Gate de contenido antes de publicar |
| `pii-detector` | NIM / gliner-pii | Detección PII en texto |
| `code-reviewer` | Anthropic / opus-4-8 | Revisión estricta de código crítico |
| `finance-specialist` | Anthropic / sonnet-4-6 | Análisis financiero, valoraciones |
| `default` | Groq / llama-3.3-70b | Fallback general |

## Salida estructurada

Todos los dispatches devuelven JSON con esta forma:

```json
{
  "task_id": "a3b4c5d6",
  "agent": "python-specialist",
  "provider": "nim",
  "model": "deepseek-ai/deepseek-v4-flash",
  "status": "ok",
  "latency_ms": 1400,
  "response": "...",
  "error": null,
  "result_file": "/root/dqiii8/tasks/results/dispatch-a3b4c5d6.json"
}
```

Posibles status: `ok` | `error` | `timeout` | `pending` (async)

## Reglas de uso

1. **Cost-first (dormante hoy)**: bajo multi-tier activo, evalúa si un tier gratuito
   (C/B/B+) puede resolverla vía dispatch antes de resolverla tú (CC/Sonnet = Tier A/S,
   de pago). Ver `.claude/rules/00_core_behavior.md` § Cost-First Rule. Bajo Anthropic-only
   (hoy), este paso no aplica — resuelve directamente con Sonnet/Opus.
2. **No dispatch para decisiones de arquitectura** — eso requiere contexto completo del proyecto que solo CC tiene.
3. **Max 6 workers en paralelo** — el NIM global rate limit es 40 RPM, evitar 429 masivos.
4. **Persistir resultados importantes**: `--project <nombre>` escribe a `tasks/results/dispatch-{id}.json`.
5. **code-reviewer (Opus) solo para código crítico** — toca ≥2 módulos, lógica de negocio, o spec ambigua.

## Conexión bidireccional CC ↔ dqiii8

```
Este CC ──dispatch.py──▶ AGENT_ROUTING ──▶ NIM/Groq/GitHub/Ollama
Este CC ◀──tasks/results/ (polling o lectura directa)

dqiii8 ──autonomous_loop.sh──▶ claude -p ──▶ Este CC
dqiii8 ◀──stdout/JSON─────────────────────────────────
```

El canal dqiii8→CC ya existe (`autonomous_loop.sh` llama `claude -p`).
El canal CC→dqiii8 es este skill + `dispatch.py`.
