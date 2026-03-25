# DQIII8 — Master Context
> Índice maestro. Reglas en `.claude/rules/`. Agentes en `.claude/agents/`.

## PROHIBICIONES ABSOLUTAS
- **NUNCA** escribir en `.env`, secrets ni credenciales.
- **NUNCA** modificar `.claude/settings.json` o `database/schema_v2.sql` sin petición explícita.
- **NUNCA** borrar datos de `dqiii8.db`.
- **NUNCA** force-push, rebase main ni borrar branches sin confirmación.
- **NUNCA** cargar skills de `skills-registry/cache/` sin revisar `INDEX.md`.
- **NUNCA** superar 3 ficheros modificados sin entrar en plan mode primero.
- **NUNCA** seguir empujando cuando algo falla. STOP → re-plan → preguntar.

## Model Routing
| Tier | Provider | Modelo | Cuándo |
|------|----------|--------|--------|
| C | Ollama | `qwen2.5-coder:7b` | código, refactor, debug, git |
| B | Groq | `llama-3.3-70b-versatile` | review, análisis, investigación |
| A | Anthropic | `claude-sonnet-4-6` | finanzas, arquitectura, orquestación |
Regla: tier más barato. Clasificar: `python3 bin/core/openrouter_wrapper.py classify "<prompt>"`

## Delegación de agentes
| Agente | Modelo | Trigger |
|--------|--------|---------|
| `python-specialist` | qwen2.5-coder:7b | código Python, tracebacks, refactor |
| `git-specialist` | qwen2.5-coder:7b | commits, branches, PRs, merge |
| `web-specialist` | qwen2.5-coder:7b | HTML/CSS/JS, scraping |
| `algo-specialist` | qwen2.5-coder:7b | algoritmos, estructuras de datos |
| `code-reviewer` | llama-3.3-70b | review de código |
| `math-specialist` | llama-3.3-70b | matemáticas, estadística |
| `finance-specialist` | claude-sonnet | WACC, DCF, análisis financiero |
| `auditor` | claude-sonnet | `/audit`, métricas del sistema |
| `orchestrator` | claude-sonnet | `/mobilize`, tareas multi-agente (3+ dominios) |
Invocar: `python3 bin/core/openrouter_wrapper.py --agent <agent> "<tarea>"`

## Autonomía (VPS mode)
- Planes ≤5 pasos sin acciones destructivas → ejecutar sin preguntar.
- Acciones destructivas o ambiguas → Telegram + esperar confirmación.
- Bug report → fix inmediato. Ver logs, resolver, verificar. Sin tutorías.
- Fix >3 ficheros o arquitectura → plan mode primero.

## Workflow
1. **Plan** — plan mode para ≥3 pasos. Spec → tasks/todo.md.
2. **Execute** — salir cuando queden ≤3 pasos concretos.
3. **Verify** — nunca marcar done sin prueba. Tests. Diff contra main.
4. **Record** — actualizar tasks/todo.md. Resumir en cada paso.
5. **Learn** — tras corrección → tasks/lessons.md: `[DATE] [KEYWORD] causa → fix`
6. **Re-plan** — si diverge, STOP. Re-planificar inmediatamente.

## Session Lifecycle
- **On start:** modelo activo + proyecto + worktrees + últimas 10 lecciones + audit score.
- **On stop:** lessons.md → projects/[project].md → DB summary → auto-commit → audit si 7d+.

## File Map
| Recurso | Ruta |
|---------|------|
| Base de datos | `database/dqiii8.db` |
| Agentes / Hooks | `.claude/agents/*.md` / `.claude/hooks/` |
| Wrapper multi-provider | `bin/core/openrouter_wrapper.py` |
| Director v3 / Telegram | `bin/director.py` / `bin/core/notify.py` |
| Knowledge | `bin/agents/knowledge_indexer.py` · `knowledge_search.py` |
| Benchmark | `bin/tools/benchmark_dq.py` |
| Smoke tests | `tests/test_smoke.py` |

## Reglas en `.claude/rules/`
- `common/`: coding-style, git-workflow, security, testing
- `dqiii8-python.md`, `dqiii8-context-window.md`, `dqiii8-prohibitions.md`
- `dqiii8-telegram.md`, `dqiii8-knowledge.md`, `dqiii8-cli-tools.md`
