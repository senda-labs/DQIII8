# Agent Orchestration — SSOT

> **Precedencia: REGLA NIM (`00_core_behavior.md`) manda sobre este fichero.** El lane de dispatch
> por `openrouter_wrapper.py` está **dormante — no invocarlo**; se delega con el Agent tool o
> `claude -p`. Routing vigente → `.claude/rules/03_tiering_and_routing.md`; historial →
> `.claude/rules_db/archive/multi-tier-dormant-2026-08.md`. Abajo se describe el cableado, no una
> ruta de ejecución.

## Two runtimes, two SSOTs (no fusionarlos)

DQIII8 tiene **dos sistemas de agentes distintos** que comparten algunos nombres.
No son un duplicado a reconciliar: son runtimes diferentes con propósitos diferentes.

| Runtime | SSOT | Qué define | Cómo se invoca |
|---|---|---|---|
| **Dispatch dqiii8** — *dormante, no invocar* (NIM / Groq / Ollama / Anthropic vía wrapper) | `AGENT_ROUTING` en `bin/core/openrouter_wrapper.py` (**código**) | Nombre de agente → `(provider, model)` | CLI del wrapper — **dormante bajo REGLA NIM**. La línea de comando no se reproduce aquí a propósito: si algún día se reactiva, sale de `python3 bin/core/openrouter_wrapper.py --help` |
| **Agent tool nativo de Claude Code** | Ficheros `.claude/agents/*.md` (**frontmatter**) | `name`, `model`, `tools`, `description` | Agent tool del propio Claude Code (Tier A por defecto) |

Solapan parcialmente: el wrapper lee el **cuerpo** de `.claude/agents/<nombre>.md` como
system prompt (`load_agent_system_prompt()`), pero **ignora su `model:`** — el modelo de
dispatch sale siempre de `AGENT_ROUTING`. Por eso un mismo nombre puede legítimamente
correr en dos modelos distintos según el runtime.

### Cómo resolver un nombre de agente (no memorizar listas)

- ¿Es válido para dispatch por Bash? → **claves de `AGENT_ROUTING`**:
  ```bash
  python3 -c "import re,sys; s=open('bin/core/openrouter_wrapper.py').read(); \
  m=re.search(r'AGENT_ROUTING = \{(.*?)\n\}', s, re.S); \
  print(sorted(re.findall(r'^\s*\"([a-z0-9\-_]+)\":', m.group(1), re.M)))"
  ```
  (no hay flag `--list-agents` en el wrapper)
- ¿Es válido para el Agent tool nativo? → **listado del directorio**: `ls .claude/agents/*.md`.
- Un nombre que no aparezca en ninguno de los dos **no existe**. No inventarlo.

Cualquier tabla de agentes escrita a mano en un `.md` es una copia derivada y se
desincroniza: si necesitas una, verifícala contra las dos fuentes anteriores en el momento.

Si encuentras un nombre de agente citado en cualquier doc, verifícalo contra las dos
fuentes de arriba antes de usarlo.

Un mismo nombre declarando modelos distintos en los dos runtimes es intencionado, no drift
(caso vivo: `research-analyst`, Groq en el fichero vs. NIM en `AGENT_ROUTING` — ambos
proveedores dormantes hoy). No lo "arregles".

### Frontmatter: campos que el runtime lee de verdad

`model:` es el único campo de modelo que el Agent tool nativo entiende. `tier:` **no lo lee
nadie** (ni Claude Code ni `openrouter_wrapper.py`, que solo parsea `domain:`) — un agente
con `tier:` y sin `model:` cae al modelo por defecto en silencio. Si documentas un tier,
acompáñalo siempre de un `model:` explícito.

## Cost-First al delegar

Delta sobre `00_core_behavior.md` § Cost-First Rule (siempre inyectada): bajo Anthropic-only
no hay tier gratuito al que bajar, así que la regla se aplica **dentro** de Anthropic —
Sonnet por defecto, Haiku donde baste, Opus solo revisión adversarial final. Nunca "ahorrar"
saltando al wrapper: está dormante (REGLA NIM).

## Cómo repartir el trabajo

- Paralelo para operaciones independientes (sin estado compartido ni dependencias);
  secuencial solo cuando haya dependencia real.
- Problemas complejos → sub-agentes con roles separados (factual, ingeniería senior,
  seguridad, consistencia, redundancia): `.claude/skills/panel-review/`.
