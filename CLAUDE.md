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

## Model Routing (4 providers)
| Tier | Provider | Modelos | Cuándo |
|------|----------|---------|--------|
| C | Ollama | `qwen2.5-coder:7b` | código, refactor, debug, git |
| B | Groq | `llama-3.3-70b-versatile` | review, análisis, investigación |
| B+ | GitHub Models | deepseek-v3, codestral, gpt-4o-mini, deepseek-r1, llama-instruct | fallback Groq, código largo |
| A | Anthropic | `claude-sonnet-4-6` | finanzas, arquitectura, orquestación |

Regla: tier más barato. Clasificar: `python3 bin/core/openrouter_wrapper.py classify "<prompt>"`

## Pipeline (7 capas)
classify → enrich(v3) → amplify → route → execute → learn → temporal

- **Enricher v3:** TOON (Tier C, minimal) | simple_json (Tier B, top chunks) | full_json (Tier A, + key_facts + metadata)
- **Knowledge:** 1309 chunks sqlite-vec, 5 dominios, hybrid_search RRF (vector+FTS5+graph), ~5.3ms KNN
- **Temporal:** fact_extractor (cron 4h), instinct_evolver (cron lunes), memory_decay (cron 4am)
- **chunk_key_facts:** pendiente poblar — `key_facts_generator.py --all`

## Delegación de agentes (27 activos)
| Agente | Modelo | Trigger |
|--------|--------|---------|
| `python-specialist` | qwen2.5-coder:7b | código Python, tracebacks, refactor |
| `git-specialist` | qwen2.5-coder:7b | commits, branches, PRs, merge |
| `web-specialist` | qwen2.5-coder:7b | HTML/CSS/JS, scraping |
| `algo-specialist` | qwen2.5-coder:7b | algoritmos, estructuras de datos |
| `code-reviewer` | llama-3.3-70b | review de código |
| `math-specialist` | llama-3.3-70b | matemáticas, estadística |
| `research-analyst` | llama-3.3-70b | investigación, síntesis |
| `finance-specialist` | claude-sonnet | WACC, DCF, análisis financiero |
| `auditor` | claude-sonnet | `/audit`, métricas del sistema |
| `orchestrator` | claude-sonnet | `/mobilize`, tareas multi-agente (3+ dominios) |
| `content-automator` | qwen2.5-coder:7b | pipeline vídeo/audio/subtítulos |

> 16 domain-specialists (biology, chemistry, etc.) usan `llama-3.3-70b` vía Groq.

Invocar: `python3 bin/core/openrouter_wrapper.py --agent <agent> "<tarea>"`

## Seguridad
- Red-team: **95/100** | AgentShield: **~85/100** | UFW: port 22 only | fail2ban: sshd
- Dashboard: `127.0.0.1:8080` (solo localhost) | SSH: PasswordAuth=no, PermitRootLogin=prohibit-password

## Autonomía (VPS mode)
- Planes ≤5 pasos sin acciones destructivas → ejecutar sin preguntar.
- Acciones destructivas o ambiguas → Telegram + esperar confirmación.
- Bug report → fix inmediato. Sin tutorías.
- Fix >3 ficheros o arquitectura → plan mode primero.

## Workflow
1. **Plan** — plan mode para ≥3 pasos.
2. **Execute** — salir cuando queden ≤3 pasos concretos.
3. **Verify** — nunca marcar done sin prueba.
4. **Record** — actualizar tasks/todo.md.
5. **Learn** — tras corrección → tasks/lessons.md: `[DATE] [KEYWORD] causa → fix`
6. **Re-plan** — si diverge, STOP y re-planificar.

## File Map
| Recurso | Ruta |
|---------|------|
| Base de datos | `database/dqiii8.db` |
| Agentes / Hooks | `.claude/agents/*.md` / `.claude/hooks/` |
| Wrapper multi-provider | `bin/core/openrouter_wrapper.py` |
| GitHub Models wrapper | `bin/core/github_models_wrapper.py` |
| Director / Telegram | `bin/director.py` / `bin/core/notify.py` |
| Enricher v3 | `bin/agents/knowledge_enricher.py` |
| Key facts generator | `bin/agents/key_facts_generator.py` |
| Benchmark multimodel | `bin/tools/benchmark_multimodel.py` |
| Reglas detalladas | `.claude/rules/` |
