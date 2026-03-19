# DQIII8 — Contexto completo para revisión con Opus 4.6
**Fecha:** 2026-03-19 | **Preparado por:** JARVIS (Sonnet 4.6 en VPS)
**Propósito:** Que Opus 4.6 analice el sistema, detecte gaps, y guíe los próximos pasos.

---

## ¿Qué es DQIII8?

Un sistema de orquestación de IA construido sobre Claude Code (VPS Ubuntu 24.04).
El usuario escribe una orden en lenguaje natural → DQIII8 la amplifica con agentes expertos en dominio → la ejecuta → aprende del resultado.

**Metáfora F1:** Los modelos de IA son el motor. DQIII8 es la transmisión, aerodinámica, telemetría y estrategia que convierte ese motor en victorias.

**Lo que hace que nadie más hace junto:**
1. Se audita a sí mismo con métricas reales (SPC — Statistical Process Control)
2. Enruta automáticamente al modelo más barato que resuelve la tarea (3 tiers)
3. Knowledge base por agente con embeddings (nomic-embed-text vía Ollama)
4. Auto-researcher que testea mejoras en sandbox antes de integrarlas
5. El usuario no necesita saber hacer prompts — el sistema amplifica

---

## Stack técnico

| Capa | Tecnología |
|------|-----------|
| Orquestador | Claude Code CLI + Python hooks |
| DB | SQLite (`database/jarvis_metrics.db`) — sesiones, acciones, errores, métricas |
| Tier 1 (local, $0) | Ollama `qwen2.5-coder:7b` — Python, debug, git ops |
| Tier 2 (cloud gratis) | Groq `llama-3.3-70b-versatile` — review, análisis, research |
| Tier 3 (paid) | Claude API `claude-sonnet-4-6` — finance, creativo, arquitectura |
| Memoria | mem0 + `vault_memory` SQLite + decay por frecuencia |
| Embeddings | `nomic-embed-text` (Ollama, 274MB) → `index.json` por agente |
| Supervisor | 3 capas: whitelist → LLM → Telegram |
| Notificaciones | Telegram bot (jarvis_bot.py) |
| Seguridad | Semgrep Shannon score 10/10, pre-commit hooks |

---

## Arquitectura de agentes

| Agente | Trigger | Modelo | Aislamiento |
|--------|---------|--------|-------------|
| orchestrator | 3+ dominios, multi-agente | claude-sonnet-4-6 | worktree |
| python-specialist | traceback, .py, refactor | qwen2.5-coder:7b | — |
| git-specialist | commit, branch, PR | qwen2.5-coder:7b | — |
| code-reviewer | review, tras feature | llama-3.3-70b | worktree |
| content-automator | video, TTS, subtítulos | nemotron-nano:free | — |
| data-analyst | WACC, DCF, Excel | claude-sonnet-4-6 | — |
| creative-writer | capítulo, escena, novela | claude-sonnet-4-6 | — |
| auditor | /audit, métricas | claude-sonnet-4-6 | — |
| finance-analyst | acciones, opciones, riesgo | claude-sonnet-4-6 | — |
| quant-analyst | backtesting, VaR, Sharpe | claude-sonnet-4-6 | — |

Routing: `python3 bin/openrouter_wrapper.py classify "[prompt]"` → devuelve tier, provider, modelo.

---

## Sistema de auto-mejora

```
Sesión termina
    │
    ├── stop.py hook → guarda estado en claude-progress.txt
    ├── postcompact.py → reinyecta contexto esencial en nueva sesión
    ├── lessons_consolidator.py → extrae patrones de lessons.md
    │
    └── Cada 7 días → /audit
            │
            ├── Queries a agent_actions, error_log, sessions, skill_metrics
            ├── Vistas: agent_performance, error_keywords_freq
            ├── Score 0-100 (SPC thresholds)
            └── Reporte → database/audit_reports/audit-YYYY-MM-DD-HH.md
```

**Tablas principales en jarvis_metrics.db:**
- `sessions` — cada sesión con start/end/status
- `agent_actions` — cada tool call con agente, duración, éxito/fallo
- `error_log` — errores con keyword, causa, resolved flag
- `skill_metrics` — métricas de skills usadas
- `vault_memory` — memoria semántica con decay
- `audit_reports` — historial de scores

---

## Estado actual (2026-03-19)

### Health Score: 81-90/100 — HEALTHY
*(varía según si se cuentan agent_actions failures vs error_log)*

| Métrica (últimos 7 días) | Valor |
|--------------------------|-------|
| Sesiones totales | 153 |
| Actions totales | 8,294 |
| Action success rate | 99.6% |
| Errors logged | 18 |
| Errors resolved | 6 (33%) |
| Error resolution rate | **33% — GAP CRÍTICO** |

### Gap conocido #1: error_log pipeline roto
23 fallos en `agent_actions` (success=0) NO aparecen en `error_log`.
El componente de "unresolved errors" en el score es artificialmente bueno.

### Gap conocido #2: lección capture en 0%
El pipeline de auto-aprendizaje implícito no está capturando lecciones.
Solo se capturan lecciones cuando el usuario corrige explícitamente.
Sesiones con errores → 0 lecciones añadidas en 5 sesiones consecutivas.

### Gap conocido #3: agent identity degradada
113 acciones tagged `unknown`, 37+ agentes con UUID en vez de nombre semántico.
La tabla `agent_performance` pierde trazabilidad.

---

## Bloques completados (6/10)

- **Bloque 0** ✅ Bootstrap VPS, estructura base
- **Bloque 1** ✅ Claude Code 2026 features, routing real (3 tiers operativos)
- **Bloque 2** ✅ Director v3, knowledge/ por agente, Agent Teams
- **Bloque 3** ✅ mem0, Shannon 10/10, contexts, security
- **Bloque 4** ✅ Auditor SPC, auto-researcher, sandbox, modo sueño
- **Bloque 5** ✅ Supervisor 3-layer, autonomous_loop.sh, bypassPermissions
- **Bloque 6** 🔄 Open source release (install.sh, README, LICENSE — casi listo)

## Bloques pendientes (4/10)

- **Bloque 4.5** 🔴 ALTA PRIORIDAD — 5 agentes de dominio del conocimiento:
  - Norte: Ciencias Formales (matemáticas, lógica, computación)
  - Este: Ciencias Naturales (física, química, biología)
  - Sur: Ciencias Sociales (economía, finanzas, derecho)
  - Oeste: Humanidades y Artes (literatura, filosofía, historia)
  - Centro: Ciencias Aplicadas (ingeniería, medicina, tecnología)
  - **Función:** clasifican y amplían el prompt del usuario ANTES de pasarlo al agente funcional

- **Bloque 7** UI/web — Codeman Respawn + CloudCLI plugins + push notifications
- **Bloque 8** Benchmark real 3 tiers (¿cuánto ahorra Tier 1 vs Tier 3?)
- **Bloque 9** Graphiti temporal memory (reemplaza mem0 SQLite)
- **Bloque 10** Knowledge passport entre proyectos

---

## Proyectos activos sobre DQIII8

| Proyecto | Estado | Descripción |
|---------|--------|-------------|
| content-automation-faceless | Activo | Pipeline video→TTS→subtítulos→reels (YouTube Shorts/TikTok) |
| leyendas-del-este | Activo | Novela xianxia generada con creative-writer |
| math-image-generator | Pausado | Fractales + compositing SSIM para miniaturas |
| hult-finance | Completado | Análisis WACC/DCF para presentación universitaria |

---

## Estructura de archivos clave

```
dqiii8/                          ← repo público (se llamaba jarvis/)
├── bin/
│   ├── j.sh                     ← entry point: j --model local|groq|sonnet
│   ├── openrouter_wrapper.py    ← classify + routing
│   ├── ollama_wrapper.py        ← Tier 1 local
│   ├── auditor.py               ← genera audit reports
│   ├── auto_researcher.py       ← busca mejoras, testea en sandbox
│   ├── autonomous_loop.sh       ← modo 24/7 sin supervisión
│   ├── autonomous_watchdog.py   ← supervisor de procesos autónomos
│   ├── knowledge_indexer.py     ← chunks + nomic-embed → index.json
│   ├── knowledge_search.py      ← cosine similarity sobre index.json
│   ├── memory_manager.py        ← vault_memory CRUD + decay
│   └── jarvis_bot.py            ← Telegram bot para control remoto
├── .claude/
│   ├── agents/                  ← definiciones de agentes en Markdown
│   ├── hooks/                   ← pre_tool_use.py, post_tool_use.py, stop.py
│   ├── rules/                   ← CLAUDE.md incluye estas reglas por referencia
│   └── settings.json            ← bypassPermissions, allowedTools, hooks config
├── config/
│   └── .env.example             ← template con todos los keys comentados
├── database/
│   ├── schema.sql               ← DDL completo
│   └── audit_reports/           ← reportes MD generados por /audit
├── tasks/
│   ├── lessons.md               ← log de auto-aprendizaje
│   └── todo.md                  ← solo OrchestratorLoop escribe aquí
├── skills-registry/             ← skills reutilizables, INDEX.md como catálogo
├── CLAUDE.md                    ← constitución del sistema (reglas, routing, agentes)
├── PLAN_MAESTRO.md              ← visión de bloques, completados y pendientes
├── install.sh                   ← Ubuntu 22.04/24.04 one-liner installer
├── README.md                    ← documentación pública
└── CONTRIBUTING.md              ← guía de contribución
```

---

## Problemas recientes (lessons.md)

**Más urgentes sin resolver:**
- [2026-03-18] [ReadError] × múltiples — archivos no encontrados desde /root/jarvis (directorio incorrecto al subagents)
- [2026-03-18] [BashError] Exit 127 — claude-progress.txt path no encontrado en hooks
- [2026-03-19] [BashError] Exit 2 — LICENSE no existía (ya corregido hoy)

**Patrones recurrentes que frenan la auto-mejora:**
- error_log no captura fallos de agent_actions (pipeline roto)
- lecciones sólo se añaden con corrección explícita del usuario
- agent identity perdida en 113+ acciones → trazabilidad reducida

---

## Preguntas para Opus 4.6

1. **Arquitectura de Bloque 4.5** — ¿Cómo diseñarías los 5 agentes de dominio del conocimiento? ¿Deben ser prompts estáticos, knowledge bases con embeddings, o algo más sofisticado? ¿Cómo clasifican el prompt del usuario antes de pasarlo al agente funcional?

2. **Error pipeline roto** — Los fallos en agent_actions no llegan a error_log. El hook post_tool_use.py debería capturarlos. ¿Qué patrón de error handling recomiendas para garantizar que todo fallo se persiste?

3. **Auto-aprendizaje implícito** — 0 lecciones en 5 sesiones consecutivas. El sistema sólo aprende cuando el usuario corrige. ¿Cómo diseñarías un pipeline que detecte patrones de error automáticamente y genere lecciones sin intervención humana?

4. **Graphiti vs mem0 SQLite** — El Bloque 9 propone reemplazar mem0 con Graphiti (memoria temporal con grafo). ¿Vale la pena la complejidad? ¿O hay algo intermedio más pragmático para un VPS con 8GB RAM?

5. **Bloque 7 UI** — ¿Qué stack recomendarías para una UI mínima que exponga DQIII8 sin romper el flujo CLI-first? ¿FastAPI + htmx? ¿Solo Telegram bot mejorado? ¿Algo más?

6. **Open source strategy** — El repo se publica como DQIII8. ¿Qué falta para que sea adoptable por otros? ¿Qué haría que alguien con un VPS lo usara en vez de ChatGPT?

7. **Benchmarks reales** — ¿Cómo medirías cuánto ahorra el sistema en tokens/coste frente a usar Claude directamente para todo? ¿Qué métricas serían las más convincentes para mostrar el valor del routing de 3 tiers?

---

## Contexto adicional

- **VPS:** Ubuntu 24.04, 8GB RAM, CPU-only (sin GPU)
- **Usuario:** Iker, developer independiente, usa el sistema para múltiples proyectos
- **Filosofía:** "Tier más bajo que resuelva la tarea. Subir solo si el inferior falla."
- **Repo actual:** `github.com/ikermartiinsv-eng/jarvis` (privado, se renombrará a dqiii8)
- **Claude Code version:** 2026 (incluye Agent Teams, bypassPermissions, MCP servers)
- **CLAUDE.md:** 100 líneas, es la "constitución" del sistema — lo primero que lee Claude al arrancar
