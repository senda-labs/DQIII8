---
name: jarvis-agent-creation
version: 1.0.0
source: git-analysis/jarvis
analyzed_commits: 50
analyzed_date: 2026-03-12
repos: [/root/jarvis]
---

# JARVIS Agent Creation

## Patrón detectado

Los agentes JARVIS se crean en "olas" (batches) con estructura idéntica.
Cada agente define: trigger, role, protocol (numerado), feedback format, y rules.

**Evidencia del historial:**
- `feat: Agentes Ola 2 — data-analyst, creative-writer, research-analyst` (2aadb19) — 3 archivos simultáneos
- `feat: routing unificado 3 tiers — Ollama+Groq+OpenRouter+Sonnet` (ba60bc7) — incluye code-reviewer, content-automator, git-specialist
- `feat: agente content-automator` (dd01d41) — agente individual con iteración
- `feat: Fase 1 completa - agentes Ola 1` — primer batch

**Co-cambios detectados:**
- `.claude/agents/*.md` siempre va con actualización de routing en `CLAUDE.md` y/o `bin/openrouter_wrapper.py`

## Cuándo usar esta skill

- Crear un nuevo agente especializado
- Añadir un agente para un nuevo dominio (ej: DevOps, mobile, finanzas)
- Revisar si un agente existente cubre el trigger antes de crear uno nuevo
- Definir el modelo correcto por tier para el agente

## Estructura canónica de un agente JARVIS

Archivo: `.claude/agents/{nombre-agente}.md`

```markdown
---
name: {nombre-agente}
model: {tier}:{modelo}
isolation: worktree  # solo si escribe código que puede romper el repo
---

# {Nombre Legible}

## Trigger
{keyword1} | {keyword2} | "frase de ejemplo" | {condición}.

## Role
{Una oración: qué hace, qué NO hace}.

## Protocol
1. {Primer paso concreto y verificable}.
2. {Segundo paso}.
3. {Verificación explícita}.
4. Write result to `tasks/results/{agente}-[timestamp].md`.

## Feedback format
\```
[NOMBRE] ✅/❌ {resumen en 1 línea}
{métrica clave}: {valor}
\```

## Rules
- {Regla específica de dominio}.
- Escalar a orchestrator si {condición de complejidad}.
```

## Agentes existentes (no duplicar)

| Agente | Modelo | Triggers clave |
|--------|--------|---------------|
| python-specialist | ollama:qwen2.5-coder:7b | .py, traceback, refactor, debug |
| git-specialist | ollama:qwen2.5-coder:7b | commit, branch, PR, merge, push |
| code-reviewer | groq:llama-3.3-70b-versatile | review, "is this ok", worktree |
| orchestrator | claude-sonnet-4-6 | /mobilize, coordinate, 3+ domains |
| content-automator | openrouter/nvidia/nemotron | video, TTS, subtítulos, reels |
| data-analyst | claude-sonnet-4-6 | WACC, DCF, chart, Excel |
| creative-writer | openrouter/meta-llama/llama-3.3-70b | chapter, scene, novel, xianxia |
| auditor | claude-sonnet-4-6 | /audit, "what's failing", metrics |
| research-analyst | openrouter/stepfun/step-3.5-flash | research, investigar, documentar |

## Workflow: crear nuevo agente

### 1. Verificar que no existe cobertura

```bash
grep -r "trigger\|Trigger" /root/jarvis/.claude/agents/ | grep -i "{tu-keyword}"
```

### 2. Elegir modelo según CLAUDE.md tier routing

- Tarea simple/local → `ollama:qwen2.5-coder:7b`
- Review/análisis → `groq:llama-3.3-70b-versatile`
- Media/contenido → `openrouter/nvidia/nemotron-nano-12b-v2-vl:free`
- Arquitectura/finanzas/creative → `claude-sonnet-4-6`

### 3. Crear el archivo `.claude/agents/{nombre}.md`

Usar la estructura canónica. Puntos críticos:
- **Trigger**: frases exactas que el usuario dice, no conceptos abstractos
- **Protocol**: siempre numerado, último paso = write to `tasks/results/`
- **Feedback format**: siempre incluir prefijo `[NOMBRE]` en mayúsculas

### 4. Registrar en `bin/openrouter_wrapper.py` si usa OpenRouter/Groq

```python
AGENT_ROUTING = {
    "{nombre-agente}": ("{provider}", "{modelo-id}"),
}
```

### 5. Actualizar tabla Delegation en `CLAUDE.md`

```markdown
| {trigger keywords} | {nombre-agente} | {isolation o —} |
```

### 6. Commit

```bash
# Si es un batch de agentes:
git commit -m "feat: Agentes Ola N — {agente1}, {agente2}, {agente3}"

# Si es agente individual con iteración:
git commit -m "feat: agente {nombre-agente}"
```

## Archivos involucrados

| Archivo | Cuándo tocarlo |
|---------|---------------|
| `.claude/agents/{nombre}.md` | Siempre (archivo principal) |
| `CLAUDE.md` § Delegation | Siempre (tabla de routing) |
| `bin/openrouter_wrapper.py` | Si usa OpenRouter/Groq (AGENT_ROUTING) |
| `bin/j.sh` | Solo si necesita flag especial en CLI |

## Anti-patrones detectados (de commits fix:)

- **Trigger demasiado genérico** → colisiones entre agentes; ser específico con frases exactas
- **No actualizar CLAUDE.md Delegation** → el agente existe pero nunca se invoca automáticamente
- **Olvidar el paso `Write result to tasks/results/`** → el orchestrator no puede leer el output
- **Usar `isolation: worktree` innecesariamente** → ralentiza; solo si escribe código que puede romper el repo
- **Modelo incorrecto** → no usar claude-sonnet-4-6 para tareas tier-1; respetar el tier routing
