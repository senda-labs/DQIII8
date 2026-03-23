# DQIII8 — Master Context

> Índice maestro para Claude Code. Lee esto antes de actuar.
> Reglas completas en `.claude/rules/`. Agentes en `.claude/agents/`.

## Identidad del proyecto

**DQIII8** es un sistema de IA autónomo que corre en VPS. Gestiona pipelines de vídeo/contenido, knowledge bases, benchmarks y operaciones Git. El desarrollador supervises it remotely via Telegram..

---

## PROHIBICIONES ABSOLUTAS (máxima prioridad)

- **NUNCA** escribir en `.env`, secrets ni credenciales.
- **NUNCA** modificar `.claude/settings.json` o `database/schema_v2.sql` sin petición explícita.
- **NUNCA** borrar datos de `dqiii8.db`.
- **NUNCA** force-push, rebase main ni borrar branches sin confirmación.
- **NUNCA** cargar skills de `skills-registry/cache/` sin revisar su estado en `INDEX.md`.
- **NUNCA** superar 3 ficheros modificados sin entrar en plan mode primero.
- **NUNCA** seguir empujando cuando algo falla. STOP → re-plan → preguntar.

---

## Rutas clave

| Recurso | Ruta |
|---------|------|
| Base de datos | `database/dqiii8.db` |
| Agentes Claude Code | `.claude/agents/*.md` |
| Reglas detalladas | `.claude/rules/` |
| Hooks | `.claude/hooks/` |
| Wrapper multi-provider | `bin/core/openrouter_wrapper.py` |
| Wrapper Ollama | `bin/core/ollama_wrapper.py` |
| Notificaciones Telegram | `bin/core/notify.py` |
| Indexer knowledge | `bin/agents/knowledge_indexer.py` |
| Search knowledge | `bin/agents/knowledge_search.py` |
| Benchmark | `bin/monitoring/benchmark_knowledge.py` |
| Domain lens engine | `bin/agents/domain_lens.py` |
| Intent amplifier | `bin/agents/intent_amplifier.py` |
| Director v3 | `bin/director.py` |
| Smoke tests | `tests/test_smoke.py` |

---

## Model Routing — 3 Tiers

| Tier | Provider | Modelo | Cuándo |
|------|----------|--------|--------|
| C (local) | Ollama | `qwen2.5-coder:7b` | código, refactor, debug, git |
| B (cloud free) | Groq | `llama-3.3-70b-versatile` | review, análisis, investigación |
| A (paid) | Anthropic | `claude-sonnet-4-6` | finanzas, arquitectura, orquestación |

**Regla:** usar el tier más barato que resuelva la tarea.

Clasificar con: `python3 bin/core/openrouter_wrapper.py classify "<prompt>"`

---

## Delegación de agentes

| Agente | Modelo | Cuándo delegar |
|--------|--------|----------------|
| `python-specialist` | qwen2.5-coder:7b | Código Python, tracebacks, refactor |
| `git-specialist` | qwen2.5-coder:7b | Commits, branches, PRs, merge |
| `web-specialist` | qwen2.5-coder:7b | HTML/CSS/JS, scraping |
| `algo-specialist` | qwen2.5-coder:7b | Algoritmos, estructuras de datos |
| `code-reviewer` | llama-3.3-70b | Review de código |
| `math-specialist` | llama-3.3-70b | Matemáticas, estadística |
| `finance-specialist` | claude-sonnet | WACC, DCF, análisis financiero |
| `auditor` | claude-sonnet | `/audit`, métricas del sistema |
| `orchestrator` | claude-sonnet | `/mobilize`, tareas multi-agente (3+ dominios) |

> Los agentes especializados de dominio (biology, chemistry, history, etc.) usan `llama-3.3-70b` vía Groq.

**Invocar via wrapper** (Tier C/B, no consume Sonnet):
```bash
python3 bin/core/openrouter_wrapper.py --agent python-specialist "<tarea>"
```

**Domain specialists** usan `domain_lens.py` para enrichment automático — el system prompt se genera dinámicamente con knowledge chunks del índice.
**Core agents** usan el MD completo como system prompt (sin domain lens).

---

## Autonomía (VPS mode)

- Planes ≤5 pasos sin acciones destructivas → ejecutar sin preguntar.
- Acciones destructivas o intención ambigua → notificar por Telegram y esperar.
- Bug report → fix inmediato. Ver logs, resolver, verificar. Sin tutorías.
- Fix requiere >3 ficheros o toca arquitectura → entrar en plan mode primero.

---

## Knowledge System

Agentes con knowledge base: `finance-analyst`, `python-specialist`.

```bash
# Buscar en knowledge de un agente
python3 bin/agents/knowledge_search.py --agent python-specialist "async patterns"

# Re-indexar tras añadir/modificar docs
python3 bin/agents/knowledge_indexer.py --agent python-specialist
```

Knowledge dirs: `.claude/agents/{agent}/knowledge/*.md` + `index.json`

---

## Notificaciones Telegram

```python
from bin.core.notify import send_telegram
send_telegram("mensaje")
```

O desde CLI: `python3 bin/core/notify.py "mensaje"`

---

## Claude Code desde Telegram — /cc

Envía cualquier prompt a Claude Code directamente desde Telegram:

```
/cc <prompt>             — Ejecuta prompt en Claude Code (sonnet-4-6, timeout 300s)
/cc_status               — Auth, versión, último uso, uptime, rate limit
/auth_status             — Detalles del fichero ~/.claude/.credentials.json
/auth_test               — Prueba mínima de autenticación
```

**Seguridad:** solo `TELEGRAM_CHAT_ID`, rate limit 10/hora, blacklist de comandos peligrosos.
**Auth:** OAuth via `~/.claude/.credentials.json` — `CLAUDE_CODE_OAUTH_TOKEN` se elimina del entorno antes de cada llamada para evitar conflictos.
**Implementado en:** `bin/ui/telegram_bot.py` (rename from `jarvis_bot.py` in your installation)

---

## Reglas detalladas (leer si el contexto lo requiere)

- `.claude/rules/common/coding-style.md` — inmutabilidad, organización ficheros
- `.claude/rules/common/git-workflow.md` — commits convencionales, PRs
- `.claude/rules/common/security.md` — checklist antes de commit
- `.claude/rules/common/testing.md` — TDD, 80% coverage mínimo
- `.claude/rules/dqiii8-python.md` — Black, pathlib, asyncio
- `.claude/rules/dqiii8-context-window.md` — zonas verde/amarillo/naranja/rojo
- `.claude/rules/dqiii8-prohibitions.md` — prohibiciones completas
