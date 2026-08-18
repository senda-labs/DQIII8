# Agent Orchestration — SSOT

## Two runtimes, two SSOTs (no fusionarlos)

DQIII8 tiene **dos sistemas de agentes distintos** que comparten algunos nombres.
No son un duplicado a reconciliar: son runtimes diferentes con propósitos diferentes.

| Runtime | SSOT | Qué define | Cómo se invoca |
|---|---|---|---|
| **Dispatch dqiii8** (NIM / Groq / Ollama / Anthropic vía wrapper) | `AGENT_ROUTING` en `bin/core/openrouter_wrapper.py` (**código**) | Nombre de agente → `(provider, model)` | `python3 bin/core/openrouter_wrapper.py --agent <nombre> --no-enrich "<prompt>"` |
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
  (no hay flag `--list-agents` en el wrapper; verificado 2026-08-17)
- ¿Es válido para el Agent tool nativo? → **listado del directorio**: `ls .claude/agents/*.md`.
- Un nombre que no aparezca en ninguno de los dos **no existe**. No inventarlo.

Cualquier tabla de agentes escrita a mano en un `.md` es una copia derivada y se
desincroniza: si necesitas una, verifícala contra las dos fuentes anteriores en el momento.

### Estado verificado 2026-08-17 (ilustrativo, no normativo)

- `AGENT_ROUTING`: 43 claves (incluida `default`). Familias: specialists de dominio en Groq,
  código/análisis en NIM, `code-reviewer` / `code-validator` en Opus (`claude-opus-4-8`),
  `finance-specialist` / `auditor` / `orchestrator` / `tax-auditor` / `closing-specialist`
  en Sonnet (`claude-sonnet-4-6`), `git-specialist` / `content-automator` en Ollama,
  bloque Accounting-ERP en Groq.
- `.claude/agents/` (17 ficheros): `auditor`, `closing-specialist`, `code-reviewer`,
  `content-automator`, `customer-accountant`, `executor-lite`, `explorer-lite`,
  `finance-specialist`, `git-specialist`, `intl-writer`, `invoice-extractor`,
  `orchestrator`, `python-specialist`, `research-analyst`, `supplier-accountant`,
  `tax-auditor`, `web-specialist`.

Versiones previas de este fichero listaban ~10 nombres de agente que no existían en ninguno
de los dos sistemas; se eliminaron el 2026-08-17 (Gap 8). Si encuentras un nombre de agente
citado en cualquier doc, verifícalo contra las dos fuentes de arriba antes de usarlo.

### Split legítimo conocido

`research-analyst`: `.claude/agents/research-analyst.md` usa `groq/llama-3.3-70b-versatile`
(coste) para el Agent tool nativo; `AGENT_ROUTING["research-analyst"]` usa NIM Nemotron
para el dispatch por Bash. Es intencionado, no drift.

### Frontmatter: campos que el runtime lee de verdad

`model:` es el único campo de modelo que el Agent tool nativo entiende. `tier:` **no lo lee
nadie** (ni Claude Code ni `openrouter_wrapper.py`, que solo parsea `domain:`) — un agente
con `tier:` y sin `model:` cae al modelo por defecto en silencio. Si documentas un tier,
acompáñalo siempre de un `model:` explícito.

## Cost-First al delegar

Antes de usar el Agent tool nativo (Tier A, tokens Anthropic), evalúa si el trabajo lo
resuelve un tier gratuito vía el wrapper. Ver `.claude/rules/00_core_behavior.md`
§ Cost-First Rule y `.claude/rules/03_tiering_and_routing.md`.

## Ejecución paralela

Usa ejecución paralela para operaciones independientes (sin estado compartido ni
dependencias secuenciales). Secuencial solo cuando exista dependencia real.

## Análisis multi-perspectiva

Para problemas complejos, usa sub-agentes con roles separados: revisor factual, ingeniero
senior, experto en seguridad, revisor de consistencia, detector de redundancia.
Ver `.claude/skills/panel-review/`.
