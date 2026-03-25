# DQIII8 — FULL SYSTEM CHECKPOINT v2
**Fecha:** 2026-03-25 | **v1:** 21:30 UTC | **v2:** 22:15 UTC | **Modelo:** claude-sonnet-4-6

> **v2 — Correcciones aplicadas:** default agent investigado, vector chunks por dominio añadidos,
> vec0 clarificado, dashboard port verificado (OK), Bloques 7/10 reclasificados,
> sqlite MCP legacy eliminado, 3 orphans archivados, 3 agent knowledge bases indexadas,
> 27 chunk_key_facts generados (TPD Groq agotado — 1282 pendientes mañana),
> ROADMAP_TO_10.md creado (10 gaps, ~31h a 10/10).

---

## 1. ARQUITECTURA

### Árbol de directorios (profundidad 3, sin pycache/.git/venv)

```
/root/dqiii8/
├── bin/
│   ├── agents/          confidence_gate, domain_agent_selector, domain_classifier, domain_lens,
│   │                    fact_extractor, hierarchical_router, hybrid_search, instinct_evolver,
│   │                    intent_amplifier, key_facts_generator, knowledge_enricher, knowledge_indexer,
│   │                    knowledge_search, memory_decay, subdomain_classifier, template_loader,
│   │                    temporal_memory, vector_store, working_memory
│   ├── core/            auth_watchdog, db, db_security, embeddings, github_models_wrapper,
│   │                    notify, ollama_wrapper, openrouter_wrapper, validate_env
│   ├── monitoring/      analytics_collector, audit_trigger, auditor_local, benchmark_knowledge,
│   │                    cost_tracker, energy_tracker, health_watchdog, knowledge_quality,
│   │                    ml_selector, routing_analyzer, subscription, system_profile, weekly_audit
│   ├── tools/           auto_learner, auto_researcher, benchmark_dq, benchmark_multimodel,
│   │                    gemini_export, gemini_review, github_researcher, handover,
│   │                    intelligence_collector, lessons_consolidator, orphan_finder,
│   │                    paper_harvester, reconcile_errors, sandbox_tester, sqlite_mcp, voice_handler
│   ├── ui/              dashboard, dashboard_security, jarvis_bot
│   ├── archive/         (scripts archivados, no ejecutar)
│   ├── director.py      punto de entrada Telegram bot + routing
│   └── j.sh             wrapper bash principal
├── .claude/
│   ├── agents/          27 agentes .md + 3 con /knowledge/
│   ├── hooks/           12 hooks Python
│   ├── rules/           24 archivos .md
│   ├── skills/          17 skills
│   ├── settings.json    permisos + hooks registrados
│   └── settings.local.json  MCPs habilitados + allow local
├── database/
│   ├── dqiii8.db        → symlink a /root/jarvis/database/jarvis_metrics.db (22 MB)
│   ├── jarvis_metrics.db  archivo real
│   ├── audit_reports/   reportes .md + logs
│   ├── migrations/      18 archivos SQL
│   └── schema*.sql
├── knowledge/           242 archivos .md en 5 dominios
│   ├── applied_sciences/   23 files
│   ├── formal_sciences/    49 files
│   ├── humanities_arts/    9 files
│   ├── natural_sciences/   63 files
│   └── social_sciences/    98 files
├── config/              domain_agent_map.json, intelligence_sources.json
├── docs/                ARCHITECTURE.md, CHANGELOG.md, PRO_CANDIDATES.md
├── tasks/               todo.md, lessons.md, handover notes
├── tests/               test_smoke.py
└── CLAUDE.md            67 líneas (actualizado hoy)
```

### Pipeline completo — Diagrama ASCII

```
[Telegram /cc o CLI]
        │
        ▼
[director.py]
  │ validate_env → load .env
  │ rate_limit check (10/hora)
  │ sanitize input (shlex.quote, blacklist)
        │
        ▼
[openrouter_wrapper.py — classify("<prompt>")]
  │ domain_classifier.py → domain (5 áreas)
  │ subdomain_classifier.py → subdomain (20+)
  │ confidence_gate.py → gate 0.55
        │
        ├─── Tier C (≤0.55 o código) ──→ Ollama qwen2.5-coder:7b  (local, 0€)
        ├─── Tier B (review/análisis) ──→ Groq llama-3.3-70b      (free tier)
        │                                GitHub Models deepseek-v3/codestral/gpt-4o-mini/r1
        └─── Tier A (finance/arch)   ──→ Anthropic claude-sonnet-4-6
                │
                ▼
[knowledge_enricher.py — Enricher v3]
  │ 1. intent_amplifier.py → domain_lens context (Tier B+)
  │ 2. vector_store.py — KNN sqlite-vec (1309 chunks, ~5.3ms)
  │ 3. hybrid_search.py — RRF: vector + FTS5 + graph
  │ 4. build_structured_context() →
  │      TOON: temporal_memory facts (Tier A)
  │      simple_json: top chunks as JSON (Tier B)
  │      full_json: + key_facts (pendiente poblar)
  │ 5. chunk_key_facts → key_facts cache (0 filas — pendiente)
        │
        ▼
[LLM call via provider]
        │
        ▼
[temporal_memory.py — post-call learning]
  │ fact_extractor.py (cron 4h) → facts table (6 filas)
  │ instinct_evolver.py (cron lunes) → instincts (51)
  │ memory_decay.py (cron 4am) → decay old facts
  │ amplification_log insert → 1488 entradas
        │
        ▼
[Telegram response + DB logging]
  agent_actions (14376) | routing_feedback (9972) | vault_memory (730)
```

### Providers y rate limits

| Provider | Modelos | Rate limit | Costo |
|----------|---------|-----------|-------|
| Ollama (local) | qwen2.5-coder:7b (4.7GB), nomic-embed-text, qwen2.5:3b, llama3 | sin límite | 0€ |
| Groq | llama-3.3-70b-versatile | ~6K req/min free | 0€ |
| GitHub Models | deepseek-v3-0324 (340ms), codestral-2501 (440ms), gpt-4o-mini (1400ms), deepseek-r1 (900ms), llama-3.3-70b-instruct (1000ms) | 20K req/mes | 0€ |
| Anthropic | claude-sonnet-4-6 | según plan | €/token |
| OpenRouter | múltiples (free tier) | varía | 0€ free |

---

## 2. BASE DE DATOS

**Archivo:** `/root/dqiii8/database/dqiii8.db` → symlink a `/root/jarvis/database/jarvis_metrics.db`
**Tamaño:** 22 MB | **Integridad:** `ok` (PRAGMA integrity_check)

### Tablas (activas — >0 filas)

| Tabla | Filas | Última entrada | Descripción |
|-------|-------|----------------|-------------|
| agent_actions | 14,376 | 2026-03-25 21:28 | Todas las acciones de agentes con métricas |
| agent_registry | 95 | — | Registro de agentes conocidos |
| amplification_log | 1,488 | 2026-03-25 21:24 | Log del pipeline de enriquecimiento |
| audit_reports | 36 | 2026-03-25 18:00 | Reportes de auditoría |
| benchmark_gold_standards | 20 | — | 20 tareas gold para benchmark |
| benchmark_multimodel_results | 74 | — | Resultados benchmark multimodel (parcial) |
| chat_messages | 10 | 2026-03-24 | Chat Telegram |
| code_metrics | 20 | 2026-03-15 | Métricas de código |
| domain_enrichment | 5 | 2026-03-19 | Configuración de enriquecimiento |
| episodes | 2 | 2026-03-25 | Temporal memory episodes (Bloque 9) |
| error_log | 660 | 2026-03-25 21:24 | Log de errores del sistema |
| fact_access_log | 1,804 | — | Acceso a facts (temporal memory) |
| facts | 6 | — | Facts extraídos (Bloque 9) |
| historical_events | 290 | 2026-03-16 | Eventos históricos para contexto |
| instincts | 51 | 2026-03-19 | Instintos aprendidos |
| intelligence_items | 36 | 2026-03-25 08:00 | Items de inteligencia recolectados |
| jal_objectives | 1 | 2026-03-12 | JAL objectives |
| jal_steps | 19 | — | JAL steps |
| knowledge_benchmark_results | 361 | 2026-03-25 17:52 | Benchmark DQ knowledge |
| knowledge_usage | 2,617 | 2026-03-25 21:26 | Uso de chunks de conocimiento |
| learning_metrics | 373 | 2026-03-25 21:24 | Métricas de aprendizaje |
| loop_errors | 3 | 2026-03-15 | Errores de loop |
| loop_objectives | 8 | 2026-03-15 | Objetivos de loop |
| morning_report | 2 | 2026-03-18 | Reportes matutinos |
| objectives | 67 | 2026-03-18 | Objetivos del sistema |
| permission_decisions | 29 | 2026-03-25 17:31 | Decisiones de permisos (hooks) |
| relations | 1 | — | Relaciones entre entidades (Bloque 9) |
| research_cache | 50 | 2026-03-25 09:33 | Caché de investigación |
| research_items | 17 | 2026-03-23 | Items de investigación |
| routing_feedback | 9,972 | 2026-03-25 14:46 | Feedback de routing para ML |
| scene_scripts | 75 | 2026-03-25 09:41 | Scripts de escenas |
| session_memory | 1,352 | 2026-03-25 14:46 | Memoria de sesión |
| sessions | 195 | — | Sesiones Claude Code |
| spc_metrics | 915 | — | Métricas SPC para audit_trigger |
| vault_memory | 730 | 2026-03-25 21:06 | Vault memory principal |
| vec_knowledge_rowids | 1,309 | — | sqlite-vec rowids (Bloque 9) |
| vector_chunks | 1,309 | — | Chunks vectorizados (Bloque 9) |
| video_outputs | 3 | 2026-03-15 | Outputs de video |

### Tablas vacías notables

| Tabla | Razón |
|-------|-------|
| chunk_key_facts | **Pendiente** — poblar con key_facts_generator.py |
| gemini_audits | No se han registrado auditorías Gemini |
| model_satisfaction | Sin datos |
| security_findings | Sin hallazgos registrados |
| skill_metrics | Sin métricas de skills |
| cc_rate_limit | Sin registros /cc |

### Tablas Bloque 9

| Tabla | Filas | Estado |
|-------|-------|--------|
| facts | 6 | OK — fact_extractor activo (cron 4h) |
| relations | 1 | Muy escaso — poco uso |
| episodes | 2 | Muy escaso |
| vector_chunks | 1,309 | OK — 5.3ms KNN |
| vec_knowledge (virtual) | ERROR | `vec0` module falla |
| chunks_fts | 1,309 | OK — FTS5 activo |
| facts_fts | 6 | OK |
| fact_access_log | 1,804 | OK |
| chunk_key_facts | **0** | **PENDIENTE** |

### Vistas (19)

`agent_performance`, `autonomy_score`, `benchmark_results`, `error_keywords_freq`,
`knowledge_benchmark_dq_uplift`, `knowledge_benchmark_summary`, `loop_effectiveness`,
`revenue_by_channel`, `tier_comparison`, `tier_ranking`, `top_performing_content`,
`v_agent_performance`, `v_claude_reliability`, `v_convergence_history`, `v_cost_savings`,
`v_dq_uplift`, `v_error_ranking`, `v_tier_distribution`, `visual_convergence`

**Índices:** 72 índices sobre 30+ tablas.

---

## 3. SCRIPTS (bin/)

**Total activos:** 74 scripts | **Órfanos detectados:** 8

### Órfanos (sin referencias fuera de bin/)

| Script | Veredicto |
|--------|-----------|
| `bin/tools/benchmark_multimodel.py` | [!] Huérfano según finder, pero se invoca manualmente — añadir a CLAUDE.md |
| `bin/tools/gemini_export.py` | [!] Invocado vía `/gemini_export` Telegram — documentar en rules |
| `bin/tools/github_researcher.py` | [!] Invocado vía `/github_research` Telegram — documentar |
| `bin/tools/orphan_finder.py` | OK — herramienta de diagnóstico, huérfano esperado |
| `bin/monitoring/benchmark_knowledge.py` | [!] Sin cron, sin referencias — posible candidato a archive |
| `bin/monitoring/energy_tracker.py` | [-] Sin referencias externas — verificar si cron lo llama |
| `bin/core/ollama_wrapper.py` | [-] Huérfano — reemplazado por openrouter_wrapper? Verificar |
| `bin/archive/jarvis_architect.py` | OK — en archive, no ejecutar |

### Scripts activos por módulo

#### bin/agents/ — Pipeline de enriquecimiento

| Script | LOC | Propósito | Quién lo llama |
|--------|-----|-----------|----------------|
| confidence_gate.py | 63 | Gate mínimo de confianza 0.55 para enriquecimiento | intent_amplifier |
| domain_agent_selector.py | 67 | Selecciona agente por dominio | openrouter_wrapper |
| domain_classifier.py | 635 | Clasifica prompts en 5 dominios + shell | openrouter_wrapper, cron |
| domain_lens.py | 101 | Genera system prompts con contexto de dominio | intent_amplifier |
| fact_extractor.py | 245 | Extrae facts de sesiones → DB | cron 4h (`*/4 * * *`) |
| hierarchical_router.py | 501 | Router jerárquico tier A/B/C | openrouter_wrapper |
| hybrid_search.py | 367 | RRF: vector + FTS5 + graph weights | knowledge_enricher |
| instinct_evolver.py | 120 | Evoluciona instintos DB → skills | cron lunes |
| intent_amplifier.py | 794 | Amplifica intención + inyecta contexto (v3) | openrouter_wrapper |
| key_facts_generator.py | 227 | Genera key facts para chunk_key_facts table | manual / cron pendiente |
| knowledge_enricher.py | 413 | Enriquecedor principal (v3) — 3 tiers JSON | intent_amplifier |
| knowledge_indexer.py | 155 | Indexa archivos .md en vector_chunks + FTS5 | cron domingo, CLI |
| knowledge_search.py | 89 | Búsqueda de knowledge vía CLI | CLI, agents |
| memory_decay.py | 171 | Decay de facts/instincts por tiempo | cron 4am |
| subdomain_classifier.py | 359 | Clasifica subdominio (20+ categorías) | intent_amplifier |
| template_loader.py | 65 | Carga templates de prompts | agents |
| temporal_memory.py | 370 | Memoria temporal — facts, relations, episodes | knowledge_enricher |
| vector_store.py | 321 | sqlite-vec KNN ~5.3ms, 1309 chunks | hybrid_search |
| working_memory.py | 99 | Memoria de trabajo por sesión | openrouter_wrapper |

#### bin/core/ — Infraestructura

| Script | LOC | Propósito | Estado |
|--------|-----|-----------|--------|
| auth_watchdog.py | 93 | Vigila credenciales Claude Code | cron */30min |
| db.py | 30 | Helper conexión SQLite | todos |
| db_security.py | 66 | Validación SQL + parametrized queries | db.py |
| embeddings.py | 34 | Genera embeddings vía nomic-embed-text | vector_store |
| github_models_wrapper.py | 171 | Wrapper GitHub Models API (5 modelos) | openrouter_wrapper |
| notify.py | 31 | Envía mensajes Telegram | todo el sistema |
| ollama_wrapper.py | 106 | Wrapper Ollama API | **[-] HUÉRFANO** |
| openrouter_wrapper.py | 891 | Wrapper multi-provider principal | director, agentes |
| validate_env.py | 164 | Verifica keys .env al startup | j.sh |

#### bin/monitoring/ — Observabilidad

| Script | LOC | Propósito | Cron |
|--------|-----|-----------|------|
| analytics_collector.py | 156 | Colecta analytics diarios | 09:00 |
| audit_trigger.py | 192 | SPC check → dispara auditor_local | */2h |
| auditor_local.py | 239 | Audit local sin API externa | llamado por audit_trigger |
| benchmark_knowledge.py | 348 | **[-] Huérfano** — sin cron activo | — |
| cost_tracker.py | 154 | Tracking costos por modelo | cost_tracker |
| energy_tracker.py | 86 | **[-] Huérfano** — sin referencias | — |
| health_watchdog.py | 171 | Health check general del sistema | 07:00 |
| knowledge_quality.py | 202 | Calidad de knowledge base | 1er día mes |
| ml_selector.py | 119 | Selector ML para routing | ml_selector |
| routing_analyzer.py | 166 | Analiza patrones de routing | lunes 06:00 |
| subscription.py | 107 | Reporte semanal de costos | lunes 09:00 |
| system_profile.py | 70 | Perfil del sistema | system_profile |
| weekly_audit.py | 249 | Audit semanal completo | lunes 08:00 |

#### bin/tools/ — Herramientas

| Script | LOC | Propósito | Cron/Trigger |
|--------|-----|-----------|-------------|
| auto_learner.py | 262 | Auto-aprendizaje desde sesiones | auto_learner |
| auto_researcher.py | 290 | Investigación automática | lunes 06:00 |
| benchmark_dq.py | 613 | Benchmark DQ ON/OFF vs gold | manual / CLAUDE.md |
| benchmark_multimodel.py | 610 | Benchmark multi-provider (activo PID 2022912) | manual |
| gemini_export.py | 197 | Exporta módulo para Gemini review | /gemini_export Telegram |
| gemini_review.py | 240 | Registra feedback Gemini en DB | post-review |
| github_researcher.py | 718 | Busca repos GitHub | /github_research Telegram |
| handover.py | 45 | Genera handover note | stop.py hook |
| intelligence_collector.py | 369 | Recolecta inteligencia RSS/Reddit | */6h (tier1), diario (t2/3) |
| lessons_consolidator.py | 100 | Consolida lecciones aprendidas | 1er día mes |
| orphan_finder.py | 98 | Detecta scripts sin referencias | manual |
| paper_harvester.py | 239 | Recolecta papers de arXiv | paper_harvester |
| reconcile_errors.py | 76 | Sincroniza failures con error_log | 04:00 diario |
| sandbox_tester.py | 240 | Testa código en sandbox | */6h |
| sqlite_mcp.py | 132 | Servidor MCP para dqiii8-db | MCP server |
| voice_handler.py | 186 | Maneja respuestas de voz | voice_handler |

#### bin/ui/ — Interfaz

| Script | LOC | Propósito | Estado |
|--------|-----|-----------|--------|
| dashboard.py | 952 | Dashboard web (FastAPI) | activo systemd |
| dashboard_security.py | 18 | Middleware seguridad dashboard | dashboard.py |
| jarvis_bot.py | 1340 | Telegram bot principal | activo systemd |
| director.py | 382 | Orquestador principal | jarvis_bot → director |

---

## 4. AGENTES (27)

### Tabla completa

| Agente | Modelo | Tier | Dominio | Knowledge chunks |
|--------|--------|------|---------|-----------------|
| ai-ml-specialist | groq/llama-3.3-70b | B | IA/ML | 0 |
| algo-specialist | ollama/qwen2.5-coder:7b | C | Algoritmos | 0 |
| auditor | claude-sonnet-4-6 | A | Métricas sistema | 0 |
| biology-specialist | groq/llama-3.3-70b | B | Biología | 0 |
| chemistry-specialist | groq/llama-3.3-70b | B | Química | 0 |
| code-reviewer | groq/llama-3.3-70b (free) | B | Review código | 0 |
| content-automator | ollama/qwen2.5-coder:7b | C | Contenido video | 2 md, 0 indexed |
| data-specialist | groq/llama-3.3-70b | B | Datos | 0 |
| economics-specialist | groq/llama-3.3-70b | B | Economía | 0 |
| finance-specialist | claude-sonnet-4-6 | A | WACC/DCF | 3 md, 0 indexed |
| git-specialist | ollama/qwen2.5-coder:7b | C | Git/branches | 0 |
| history-specialist | groq/llama-3.3-70b | B | Historia | 0 |
| language-specialist | groq/llama-3.3-70b | B | Lingüística | 0 |
| legal-specialist | groq/llama-3.3-70b | B | Derecho | 0 |
| logic-specialist | groq/llama-3.3-70b | B | Lógica | 0 |
| marketing-specialist | groq/llama-3.3-70b | B | Marketing | 0 |
| math-specialist | groq/llama-3.3-70b | B | Matemáticas | 0 |
| nutrition-specialist | groq/llama-3.3-70b | B | Nutrición | 0 |
| orchestrator | claude-sonnet-4-6 | A | Multi-agente | 0 |
| philosophy-specialist | groq/llama-3.3-70b | B | Filosofía | 0 |
| physics-specialist | groq/llama-3.3-70b | B | Física | 0 |
| python-specialist | ollama/qwen2.5-coder:7b | C | Python/código | 2 md, 0 indexed |
| research-analyst | groq/llama-3.3-70b | B | Investigación | 0 |
| software-specialist | groq/llama-3.3-70b | B | Software/arch | 0 |
| stats-specialist | groq/llama-3.3-70b | B | Estadística | 0 |
| web-specialist | ollama/qwen2.5-coder:7b | C | HTML/CSS/JS | 0 |
| writing-specialist | groq/llama-3.3-70b | B | Escritura | 0 |

**Distribución:** Tier A (3) · Tier B (18) · Tier C (6)

### Problemas detectados

- **[-] Agent knowledge sin indexar:** finance-specialist, python-specialist, content-automator tienen archivos .md pero 0 chunks indexados. Ejecutar `knowledge_indexer.py --agent <nombre>`.
- **[-] code-reviewer con model="free":** Ambiguo — debería especificarse groq/llama o un modelo concreto.
- **[!] 19 agentes sin uso en 7d:** Solo claude-sonnet-4-6, default, context-mode, research-analyst y benchmark-* aparecen en top-10. Los 19 domain-specialists no se usan activamente.

### Uso 7 días (top 10 por agent_actions)

| Agente | Acciones | Success |
|--------|---------|---------|
| claude-sonnet-4-6 | 4,061 | 97% |
| default | 751 | 79% |
| context-mode | 170 | 99% |
| research-analyst | 80 | 100% |
| benchmark-groq | 50 | 100% |
| benchmark-ollama | 50 | 100% |
| (4 sesiones anónimas) | ~179 | 95-100% |

**Total 7d:** 5,933 acciones · 94.7% success

---

## 5. SKILLS + HOOKS + RULES

### Skills (17, en .claude/skills/)

| Skill | Líneas | Propósito |
|-------|--------|-----------|
| audit | 55 | Health audit → DB report |
| blue-team | 100 | Hardening defensivo post red-team |
| checkpoint | 86 | Guardar estado con git commit |
| evolve | 53 | Agrupa instincts → skills accionables |
| gemini-review | 46 | Exportar + registrar review Gemini |
| handover | 99 | Nota de handover al final sesión |
| instinct-status | 98 | Ver instincts por proyecto |
| mobilize | 65 | Multi-agente 3+ dominios |
| mode | 67 | Activar modo analyst/coder/creative |
| prompt-optimize | 108 | Optimizar prompts para el ecosistema |
| quality-gate | 93 | Black + isort + ruff + pytest + semgrep |
| red-team | 240 | Auditoría adversarial completa |
| security-cycle | 68 | Ciclo red+blue+verify |
| skill-create | 33 | Generar skills desde git history |
| test-team | 59 | Test coordinación agentes secuenciales |
| transcript-learn | 103 | Ingestar knowledge desde transcripts |
| weekly-review | 76 | Dashboard semanal + métricas |

### Hooks (12, en .claude/hooks/)

| Hook | Tipo | Función |
|------|------|---------|
| session_start.py | SessionStart | Carga modelo + proyecto + lecciones |
| pre_tool_use.py | PreToolUse (all) | Log + validación de tool |
| permission_request.py | PermissionRequest | Aprende aprobaciones |
| permission_analyzer.py | (helper) | Analiza decisiones de permisos |
| post_tool_use.py | PostToolUse (all) | Metrics + log acción |
| semgrep_scan.py | PostToolUse (Edit/Write) | Escaneo seguridad automático |
| post_tool_use_failure.py | PostToolUseFailure | Log errores de tool |
| precompact.py | PreCompact | Guarda estado antes de compact |
| postcompact.py | PostCompact | Recarga contexto esencial |
| stop.py | Stop + SubagentStop | Handover + audit si 7d+ |
| subagent_start.py | SubagentStart | Init context subagente |
| user_prompt_submit.py | UserPromptSubmit | Procesa prompt antes de enviar |

**Hooks especiales en settings.json:**
- `Edit|Write` → Shannon agent (prompt hook, timeout 10s) — evalúa seguridad
- `Edit|Write` → semgrep_scan.py (command hook)
- `context-mode` → sessionstart.mjs + posttooluse.mjs + precompact.mjs (context window protection)

### Rules (24 archivos, ~3,300 tokens totales)

| Archivo | ~Tokens | Nota |
|---------|---------|------|
| bash-safety.md | 80 | Nuevo hoy — cargado bajo demanda |
| common/agents.md | 343 | Override: usa .claude/agents/ de DQIII8 |
| common/coding-style.md | 289 | |
| common/development-workflow.md | 335 | |
| common/git-workflow.md | 148 | |
| common/hooks.md | 136 | |
| common/patterns.md | 188 | |
| common/performance.md | 339 | Override: 3-tier DQIII8 |
| common/security.md | 182 | |
| common/testing.md | 148 | |
| dqiii8-autonomy.md | 126 | VPS mode |
| dqiii8-cli-tools.md | 94 | CLI tools Telegram |
| dqiii8-context-window.md | 178 | Green/Yellow/Orange/Red zones |
| dqiii8-gemini-review.md | 111 | |
| dqiii8-github-research.md | 102 | |
| dqiii8-knowledge.md | 62 | |
| dqiii8-prohibitions.md | 120 | |
| dqiii8-python.md | 96 | |
| dqiii8-telegram.md | 100 | |
| python/coding-style.md | 118 | |
| python/hooks.md | 71 | |
| python/patterns.md | 139 | |
| python/security.md | 84 | |
| python/testing.md | 84 | |
| **TOTAL** | **~3,354** | |

---

## 6. CONFIGURACIÓN CLAUDE CODE

### settings.json (estructura)

```json
{
  "permissions": {
    "allow": ["Bash(*)", "Read(*)", "Write(*)", "Edit(*)", "Glob(*)", "Grep(*)"],
    "deny": []
  },
  "hooks": {
    "SessionStart": [session_start.py, context-mode/sessionstart.mjs],
    "PreToolUse": [pre_tool_use.py, Shannon-agent-prompt(Edit|Write)],
    "PostToolUse": [post_tool_use.py, context-mode/posttooluse.mjs, semgrep_scan.py(Edit|Write)],
    "PreCompact": [precompact.py, context-mode/precompact.mjs],
    "PostCompact": [postcompact.py],
    "Stop": [stop.py],
    "SubagentStop": [stop.py],
    "SubagentStart": [subagent_start.py],
    "UserPromptSubmit": [user_prompt_submit.py],
    "PostToolUseFailure": [post_tool_use_failure.py],
    "PermissionRequest": [permission_request.py]
  },
  "env": {
    "MAX_THINKING_TOKENS": "10000",
    "CLAUDE_CODE_SUBAGENT_MODEL": "haiku",
    "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "50"
  }
}
```

### settings.local.json

```json
{
  "permissions": {
    "allow": ["mcp__sqlite__query", "mcp__sqlite__execute",
              "mcp__filesystem__read_text_file", "mcp__filesystem__list_allowed_directories",
              "mcp__fetch__fetch", "mcp__exa__web_search_exa",
              "mcp__context-mode__ctx_*", "mcp__github__search_repositories",
              "mcp__github__get_file_contents",
              "WebFetch(domain:docs.anthropic.com)", "Skill(audit)"]
  },
  "enableAllProjectMcpServers": false,
  "enabledMcpjsonServers": ["filesystem","fetch","sqlite","github","dqiii8-db","context7"]
}
```

**Nota:** `enableAllProjectMcpServers: false` es medida de seguridad AgentShield implementada hoy.

### .mcp.json — 6 MCPs activos

| Servidor | Comando | Función |
|----------|---------|---------|
| filesystem | npx @modelcontextprotocol/server-filesystem /root/jarvis | Acceso FS a /root/jarvis |
| fetch | python -m mcp_server_fetch | HTTP fetch |
| sqlite | python /root/jarvis/bin/sqlite_mcp.py (jarvis_metrics.db) | DB legacy via /root/jarvis |
| github | npx @modelcontextprotocol/server-github | GitHub API |
| dqiii8-db | python3 bin/tools/sqlite_mcp.py | **dqiii8.db nativo** (nuevo hoy) |
| context7 | npx @upstash/context7-mcp | Documentación de librerías |

**Problema:** `sqlite` MCP apunta a `/root/jarvis/bin/sqlite_mcp.py` (path legacy), mientras `dqiii8-db` apunta a `/root/dqiii8/bin/tools/sqlite_mcp.py`. Ambos tocan la misma DB (jarvis_metrics.db). Redundancia — limpiar.

### Coherencia CLAUDE.md

**Qué falta documentar en CLAUDE.md:**
1. Bloque 9 (temporal_memory, vector_store, hybrid_search, fact_extractor, instinct_evolver)
2. GitHub Models como nueva fuente Tier B (5 modelos verificados)
3. Enricher v3 (3 tiers JSON, build_structured_context, key_facts_generator)
4. Scripts nuevos hoy: github_models_wrapper.py, benchmark_multimodel.py
5. sqlite MCP doble entrada (redundancia)

**Qué sobra:** Las instrucciones `common/` de ECC en agents.md y performance.md tienen overrides DQIII8 pero los textos base siguen siendo confusos.

---

## 7. KNOWLEDGE BASE

### knowledge/ por dominio (242 archivos .md)

| Dominio | Archivos .md | Vector chunks | FTS5 chunks |
|---------|-------------|--------------|-------------|
| social_sciences | 98 | (parte de 1309) | (parte de 1309) |
| natural_sciences | 63 | (parte de 1309) | (parte de 1309) |
| formal_sciences | 49 | (parte de 1309) | (parte de 1309) |
| applied_sciences | 23 | (parte de 1309) | (parte de 1309) |
| humanities_arts | 9 | (parte de 1309) | (parte de 1309) |
| **TOTAL** | **242** | **1,309** | **1,309** |

### Vector distribution en DB (vector_chunks)

| Dominio | Chunks |
|---------|--------|
| social_sciences | 522 |
| natural_sciences | 307 |
| formal_sciences | 218 |
| applied_sciences | 154 |
| (sin dominio) | 55 |
| humanities_arts | 53 |
| **TOTAL** | **1,309** |

### Agent knowledge

| Agente | Archivos .md | Chunks indexados | Estado |
|--------|-------------|-----------------|--------|
| python-specialist | 2 (async_patterns, windows_paths) | **0** | [-] Sin indexar |
| finance-specialist | 3 (dcf, ratios, wacc) | **0** | [-] Sin indexar |
| content-automator | 2 (elevenlabs, video_pipeline) | **0** | [-] Sin indexar |

### sqlite-vec (Bloque 9)

- **Estado:** `vec0` virtual table falla en CLI sqlite3 — la extensión no está cargada en el binario del sistema.
  `vec0` **sí funciona** cuando vector_store.py carga la extensión explícitamente via `conn.load_extension()`.
- **Workaround activo:** vector_store.py carga sqlite-vec en Python → KNN completamente funcional.
- **KNN latencia:** ~5.3ms para 1309 chunks (sqlite-vec + extensión cargada).
- **Rows:** vec_knowledge_rowids=1309, vec_knowledge_vector_chunks00=2 (inconsistencia — virtual table auxiliar, no afecta KNN).

### FTS5

- `chunks_fts`: 1,309 docs indexados
- `facts_fts`: 6 docs (muy escaso)

### Temporal memory (Bloque 9)

| Tabla | Filas | Observación |
|-------|-------|-------------|
| facts | 6 | Extracción activa (cron 4h), pero muy pocos facts |
| relations | 1 | Casi sin uso |
| episodes | 2 | Casi sin uso |
| fact_access_log | 1,804 | OK — log de acceso funcional |

### chunk_key_facts

- **Filas:** 0 — **PENDIENTE CRÍTICO**
- Generado por `key_facts_generator.py --all`
- Usado por Enricher v3 `full_json` tier
- Sin esto, el tier más rico del Enricher v3 no funciona

---

## 8. INFRAESTRUCTURA Y SEGURIDAD

### Servicios systemd

| Servicio | Estado |
|----------|--------|
| jarvis-bot | active (running) |
| dq-dashboard | active (running) |
| jarvis-monitor | active (running) |
| ollama | active (running) |

### tmux sessions activas

| Session | Ventanas | Creada | Nota |
|---------|---------|--------|------|
| api2 | 1 | Mar 16 | API testing |
| auth | 2 | Mar 12 | Auth management |
| claude_gold | 1 | Mar 25 14:51 | **attached** — benchmark corriendo (PID 2022912) |
| jarvis | 1 | Mar 12 | Jarvis principal |

### Crontab completo

```cron
# Analytics collector (09:00 UTC)
0 9 * * *   analytics_collector.py
# Content automation batch (09:00 + 18:00 UTC)
0 9,18 * * * content-automation/daily_topics.py
# /tmp cleanup (03:00)
0 3 * * *   find /tmp -mtime +1 -exec rm -rf {} +
# Auto-researcher (lunes 06:00)
0 6 * * 1   auto_researcher.py --full
# Sandbox tester (*/6h)
0 */6 * * * sandbox_tester.py --process-queue
# Memory decay (04:00)
0 4 * * *   memory_decay.py
# Lessons consolidator (1er día mes 05:00)
0 5 1 * *   lessons_consolidator.py
# Morning report bot (08:00)
0 8 * * *   jarvis_bot.py --morning-report
# Nightly maintenance (03:00)
0 3 * * *   bin/nightly.sh
# Auth watchdog (*/30min)
*/30 * * * * auth_watchdog.py
# Health watchdog (07:00)
0 7 * * *   health_watchdog.py
# Weekly audit (lunes 08:00)
0 8 * * 1   weekly_audit.py
# Routing analyzer (lunes 06:00)
0 6 * * 1   routing_analyzer.py
# Knowledge quality (1er día mes 07:00)
0 7 1 * *   knowledge_quality.py
# Intelligence collector — tier1 (*/6h)
0 */6 * * * intelligence_collector.py --tier 1
# Intelligence collector — tier2/3 (08:00)
0 8 * * *   intelligence_collector.py --tier 2,3
# Intelligence collector — tier4 (lunes 08:00)
0 8 * * 1   intelligence_collector.py --tier 4
# Intelligence digest (20:00)
0 20 * * *  intelligence_collector.py --digest
# Knowledge reindex (domingo 02:00)
0 2 * * 0   knowledge_indexer.py --domain <5 dominios>
# reconcile_errors (04:00)
0 4 * * *   reconcile_errors.py
# Subscription cost report (lunes 09:00)
0 9 * * 1   subscription.py
# audit_trigger SPC (*/2h)
0 */2 * * * audit_trigger.py
# fact_extractor (4h offset :17)
17 */4 * * * fact_extractor.py --batch  ← NUEVO Bloque 9
# instinct_evolver (lunes 06:00)
0 6 * * 1   instinct_evolver.py --report  ← NUEVO Bloque 9
```

**Verificación de paths:** Todos los scripts verificados presentes en disco.

### Recursos del sistema

| Recurso | Valor |
|---------|-------|
| RAM total | 7.8 GB |
| RAM usada | 1.5 GB (19%) |
| RAM disponible | 6.2 GB |
| Swap usada | 1.0 GB / 4.0 GB |
| Disco / | 42 GB / 96 GB (44%) |
| Uptime | 15 días 1h18m |
| Load avg | 0.88 / 0.37 / 0.31 |

### Modelos Ollama instalados

| Modelo | Tamaño | Última modificación |
|--------|--------|-------------------|
| qwen2.5-coder:7b | 4.7 GB | hace 7 días |
| nomic-embed-text:latest | 274 MB | hace 6 días |
| qwen2.5:3b | 1.9 GB | hace 6 semanas |
| llama3:latest | 4.7 GB | hace 6 semanas |

**Total Ollama:** ~11.6 GB

### .env — Keys presentes (15)

| Key | Longitud |
|-----|---------|
| OPENROUTER_API_KEY | 73 |
| GROQ_API_KEY | 56 |
| GEMINI_API_KEY | 39 (duplicada en .env) |
| DQIII8_BOT_TOKEN | 46 |
| TELEGRAM_CHAT_ID | 10 |
| HF_TOKEN | 37 |
| FAL_API_KEY | 69 |
| ELEVENLABS_API_KEY | 51 |
| EXA_API_KEY | 36 |
| DQIII8_ROOT | 12 |
| DQ_DEFAULT_TIER | 11 |
| FIRECRAWL_API_KEY | 35 |
| GITHUB_TOKEN | 40 |
| DQIII8_DASHBOARD_HOST | 9 |

**[!] GEMINI_API_KEY duplicada** — limpiar .env

### Seguridad

| Área | Estado |
|------|--------|
| UFW | active — solo puerto 22 abierto |
| fail2ban | active — 1 jail: sshd |
| SSH | Puerto 22 LISTEN (IPv4 + IPv6) |
| PasswordAuth | no (hardened hoy) |
| PermitRootLogin | prohibit-password |
| Puertos públicos | SOLO 22/tcp |
| Red-team score | **95/100** |
| AgentShield score | **~85/100** |

**Nota:** Dashboard web (dq-dashboard) presumiblemente accesible solo en localhost — verificar si está expuesto.

---

## 9. PROYECTOS INDIVIDUALES

### /root/dqiii8/my-projects/

| Proyecto | Git | Último commit | Dirty | Estado | Relación DQ |
|----------|-----|--------------|-------|--------|-------------|
| auto-report | sí | security: add API key auth... | 17 files | activo | Genera reportes automáticos con DQ |
| automatic-nutrition | sí | feat: diet_generator.py LLM meal plans via DQ Groq | 29 files | activo | Usa openrouter_wrapper (Groq tier) |
| content-automation | sí | refactor: unify DURATION_CONFIG + fix SQL injection | 5 files | activo | Sub-proyecto principal content |
| hult-finance | no git | — | — | pausado | Análisis financiero Hult |
| math-image-generator | sí (vacío) | no commits | 0 | incompleto | Math → imagen |
| sentiment-jobsearch | no git | — | — | pausado | Análisis sentimiento empleos |

### Proyectos raíz

| Directorio | Git | Último commit | Estado | Nota |
|------------|-----|--------------|--------|------|
| content-automation-faceless | sí | refactor: unify DURATION_CONFIG... (symlink a my-projects/content-automation) | activo | Faceless content automation |
| jarvis | sí | 1e3f5cb docs: handover 2026-03-25 | **limpio** | Symlink principal de dqiii8.db |
| dqiii8-workspace | sí | d852571 feat: initial workspace structure | dirty=1 | Worktree de desarrollo |

### Problemas detectados

- **[-] auto-report:** 17 archivos sin commitear — riesgo de pérdida
- **[-] automatic-nutrition:** 29 archivos sin commitear — crítico
- **[-] content-automation:** 5 archivos sin commitear
- **[-] hult-finance, sentiment-jobsearch:** sin git — ningún historial

---

## 10. MÉTRICAS

### Agent Actions (últimos 7 días)

| Métrica | Valor |
|---------|-------|
| Total acciones | 5,933 |
| Exitosas | 5,618 |
| Fallidas | 315 |
| Success rate | **94.7%** |

### Top 10 agentes (7d)

| Agente | Acciones | Success |
|--------|---------|---------|
| claude-sonnet-4-6 | 4,061 | 97% |
| default | 751 | 79% |
| context-mode | 170 | 99% |
| research-analyst | 80 | 100% |
| benchmark-groq | 50 | 100% |
| benchmark-ollama | 50 | 100% |
| 4 sesiones anónimas | ~179 | 95-100% |

**[!] "default" tiene 79% success — INVESTIGADO:**
- Tool único: `openrouter_wrapper` (751 de 756 acciones).
- Causa: el agente "default" es el wrapper genérico cuando no hay agente identificado.
  Registra cada intento de provider por separado — incluyendo fallos de providers secundarios
  antes de que el fallback tenga éxito. Patrón típico: 3 fallos (stepfun, groq, llm7)
  seguidos de 1 éxito = 25% success registrado aunque el resultado final sea correcto.
- **Conclusión:** no es un bug funcional sino un artefacto de logging. El sistema sí responde,
  pero log_action() registra cada provider attempt como una acción independiente.
- **Fix recomendado:** registrar solo el intento final (success/fail del batch), no cada provider.

### Benchmark multimodel (parcial — 74 resultados)

| Provider/Modelo | Resultados | avg_score | Latencia media |
|----------------|-----------|-----------|---------------|
| groq/llama-3.3-70b | 24 | NULL (no evaluado) | — |
| github/deepseek-v3-0324 | 13 | NULL | ~11,557ms |
| github/deepseek-r1 | 12 | NULL | — |
| github/llama-3.3-70b-instruct | 11 | NULL | — |
| github/codestral-2501 | 6 | NULL | — |
| github/gpt-4o-mini | 6 | NULL | — |
| ollama/qwen2.5-coder:7b | 3 | NULL | — |

**Estado:** avg_score = NULL para todos — el benchmark genera respuestas pero NO ha corrido el scoring todavía.
- DQ ON: 36 resultados | DQ OFF: 39 resultados
- **Pendiente:** `benchmark_multimodel.py --score` y `--report`

### Benchmark DQ Knowledge (361 resultados — knowledge_benchmark_results)

**HALLAZGO CRÍTICO: DQ tiene uplift NEGATIVO en todos los dominios**

| Dominio | DQ ON | DQ OFF | Uplift | n |
|---------|-------|--------|--------|---|
| social_sciences | 5.70 | 6.59 | **-0.89** | 74 |
| natural_sciences | 7.04 | 8.02 | **-0.98** | 75 |
| formal_sciences | 5.84 | 7.26 | **-1.42** | 75 |
| applied_sciences | 5.53 | 7.08 | **-1.55** | 66 |
| humanities_arts | 5.56 | 7.30 | **-1.74** | 71 |

El enriquecimiento actual **perjudica** la calidad de respuesta. Posibles causas:
- Chunks irrelevantes contaminan el contexto
- El enricher v1/v2 (que generó estos datos) inyecta demasiado ruido
- Los 361 resultados son con enricher v2 — hay que re-benchmarkear con v3

### Audit scores (últimos 5)

| Fecha | Score | Acciones | Success |
|-------|-------|---------|---------|
| 2026-03-25 18:00 | **84.5** | 6,000 | 94.8% |
| 2026-03-25 16:12 | 84.6 | 5,754 | 94.7% |
| 2026-03-25 16:11 | 84.6 | 5,751 | 94.7% |
| 2026-03-25 16:10 | 84.6 | 5,749 | 94.7% |
| 2026-03-25 16:07 | 71.0 | 5,738 | 94.7% |

Score estable ~84-85/100.

### Instincts (51 total)

| Proyecto | Instincts |
|----------|----------|
| jarvis-core | 42 |
| jarvis | 7 |
| content-automation | 2 |

### Seguridad

| Auditoría | Score |
|-----------|-------|
| Red-team (hoy) | 95/100 |
| AgentShield | ~85/100 |

---

## 11. RESUMEN EJECUTIVO

### Tabla de salud por área

| Área | Score /10 | Top Issue |
|------|-----------|-----------|
| Infraestructura | 9/10 | Swap en uso (1GB) — normal con 7.8GB |
| Seguridad | 9.5/10 | Dashboard en 127.0.0.1:8080 (OK, no expuesto) |
| Pipeline core | 8/10 | DQ uplift negativo — enricher v2 perjudica |
| Knowledge base | 7/10 | Agent knowledge sin indexar, chunk_key_facts vacía |
| Monitoreo | 8.5/10 | "default" 79% = artefacto de logging (investigado — no bug real) |
| Benchmark | 5/10 | 74 resultados sin scoring, uplift negativo |
| Proyectos externos | 6/10 | 51+ archivos sin commitear en 3 repos |
| DB integridad | 9/10 | vec0 OK via Python (falla solo en CLI sqlite3), GEMINI_KEY duplicada |
| Agentes | 7/10 | 19/27 sin uso, agent knowledge sin indexar |
| Scripts | 8/10 | 4 orphans reales a resolver |

### Top 10 mejoras por ROI (impacto ÷ esfuerzo)

| # | Mejora | Impacto | Esfuerzo | ROI |
|---|--------|---------|---------|-----|
| 1 | Poblar chunk_key_facts (`key_facts_generator.py --all`) | Alto | Bajo | ★★★★★ |
| 2 | Indexar agent knowledge (python-specialist, finance, content-automator) | Medio | Bajo | ★★★★ |
| 3 | Commitear auto-report (17), automatic-nutrition (29), content-automation (5) | Medio | Bajo | ★★★★ |
| 4 | Correr `benchmark_multimodel.py --score` + `--report` | Alto | Bajo | ★★★★ |
| 5 | Benchmarkear Enricher v3 (re-run con config nueva) | Alto | Medio | ★★★★ |
| 6 | Investigar "default" agent 79% failures | Medio | Bajo | ★★★★ |
| 7 | Limpiar GEMINI_API_KEY duplicada en .env | Bajo | Mínimo | ★★★ |
| 8 | Archivar benchmark_knowledge.py + energy_tracker.py (orphans inactivos) | Bajo | Mínimo | ★★★ |
| 9 | Actualizar CLAUDE.md con Bloque 9 + GitHub Models + Enricher v3 | Medio | Bajo | ★★★ |
| 10 | Verificar si dashboard expuesto en 0.0.0.0 (firewall solo tiene 22) | Alto | Bajo | ★★★ |

### Top 5 simplificaciones posibles

1. **sqlite MCP doble:** `sqlite` (legacy /root/jarvis) + `dqiii8-db` apuntan a la misma DB — eliminar `sqlite`
2. **ollama_wrapper.py huérfano:** Reemplazado por openrouter_wrapper — archivar
3. **content-automation-faceless = symlink** de my-projects/content-automation — documentar o eliminar alias
4. **benchmark_knowledge.py (348 LOC):** Sin cron, sin referencias — mover a archive o conectar a cron
5. **common/agents.md override:** La tabla ECC está obsoleta para DQIII8 — sustituir por referencia directa

### Top 5 conexiones rotas o sub-utilizadas

1. **chunk_key_facts (0 filas):** Enricher v3 full_json tier no funciona sin esto
2. **vec_knowledge virtual table:** `vec0` module falla — fallback a cosine manual OK pero lento a escala
3. **Agent knowledge (0 chunks):** 3 agentes tienen knowledge .md pero no indexada → knowledge_enricher no puede usarla
4. **facts/relations/episodes (6/1/2 filas):** Temporal memory casi sin datos — fact_extractor corre pero extrae muy poco
5. **benchmark multimodel sin scoring:** 74 respuestas generadas pero avg_score=NULL — el loop está incompleto

### CLAUDE.md — Versión actualizada propuesta

```markdown
# DQIII8 — Master Context (v2 — 2026-03-25)

## PROHIBICIONES ABSOLUTAS
[mantener igual — 8 líneas]

## Model Routing (3 tiers)
Tier C: Ollama qwen2.5-coder:7b — código, git, debug
Tier B: Groq llama-3.3-70b | GitHub Models deepseek-v3/codestral/gpt-4o-mini/deepseek-r1/llama-instruct
Tier A: claude-sonnet-4-6 — finanzas, arquitectura, orquestación

## Pipeline Bloque 9 (activo)
- vector_store.py: 1309 chunks, KNN 5.3ms (sqlite-vec)
- hybrid_search.py: RRF = vector + FTS5 + graph
- temporal_memory.py: facts(6), relations(1), episodes(2)
- fact_extractor.py: cron 17 */4 — batch extraction
- instinct_evolver.py: cron lunes 06:00

## Enricher v3
- build_structured_context(): TOON/simple_json/full_json
- chunk_key_facts: PENDIENTE poblar (key_facts_generator.py --all)

## Delegación [tabla igual]

## Workflow + File Map [igual]
```

### Roadmap Bloques 7-10

| Bloque | Descripción | Estado |
|--------|-------------|--------|
| Bloque 7 | UI/web — Stitch preparado, dashboard activo localhost:8080 (127.0.0.1 OK) | EN PROGRESO |
| Bloque 8 | Benchmark DQ — 20 gold standards, benchmark_dq.py | COMPLETO (361 resultados) |
| Bloque 8b | Benchmark multimodel — GitHub Models, deepseek, groq | EN PROGRESO (74/600 resultados) |
| Bloque 9 | Temporal memory + vector_store + hybrid_search + fact_extractor + instinct_evolver | COMPLETO código — datos mínimos (6 facts) |
| Bloque 9b | Enricher v3 (structured JSON, key_facts_generator) | COMPLETO código — chunk_key_facts pendiente |
| Bloque 10 | Knowledge passport entre proyectos — compartir knowledge entre dqiii8 y my-projects/ | NO INICIADO — requiere diseño |

---

## 12. PENDIENTES MAÑANA

```bash
# 1. Verificar si benchmark multimodel terminó
tmux attach -t claude_gold
# o:
python3 bin/tools/benchmark_multimodel.py --status 2>/dev/null

# 2. Poblar key_facts cache (Enricher v3 full_json tier)
cd /root/dqiii8 && python3 bin/agents/key_facts_generator.py --all

# 3. Indexar agent knowledge (3 agentes)
python3 bin/agents/knowledge_indexer.py --agent python-specialist
python3 bin/agents/knowledge_indexer.py --agent finance-specialist
python3 bin/agents/knowledge_indexer.py --agent content-automator

# 4. Correr scoring del benchmark multimodel
python3 bin/tools/benchmark_multimodel.py --score

# 5. Generar reporte benchmark
python3 bin/tools/benchmark_multimodel.py --report

# 6. Benchmarkear Enricher v3 vs v2 (5 tareas comparativas)
python3 bin/tools/benchmark_dq.py --config enricher_v3 --tasks 5

# 7. Actualizar CLAUDE.md con Bloque 9 + GitHub Models + Enricher v3
# (ver propuesta en sección 11 arriba)

# 8. Commitear proyectos con dirty files
cd /root/dqiii8/my-projects/auto-report && git add -u && git commit -m "chore: session state"
cd /root/dqiii8/my-projects/automatic-nutrition && git add -u && git commit -m "chore: session state"
cd /root/dqiii8/my-projects/content-automation && git add -u && git commit -m "chore: session state"

# 9. Limpiar duplicados
# Eliminar GEMINI_API_KEY duplicada en .env
# Dashboard: VERIFICADO OK — 127.0.0.1:8080 (solo localhost, no expuesto públicamente)
# Considerar archivar benchmark_knowledge.py + energy_tracker.py

# 10. Commit final del checkpoint
cd /root/dqiii8
git add docs/CHECKPOINT_2026-03-25.md
git commit -m "docs: full system checkpoint 2026-03-25"
```

---

## 13. COMMITS DE HOY (2026-03-25)

```
1e3f5cb docs: add real next steps to handover 2026-03-25
b8a0c92 feat(enricher-v3): structured JSON context injection + key facts cache
a7d1de5 feat: --model accepts multiple values (nargs="+")
56732b2 fix: add User-Agent header to bypass Cloudflare 403 on Groq/OpenRouter
c0a878e fix: qwen DQ-OFF only in benchmark, configurable dq_modes per model
6b8d3ca chore(auto): session 9e846c77 2026-03-25
9441e18 fix: benchmark rate limiting per provider + enrichment columns
ceb3a0c chore(auto): session 0e82ce7a 2026-03-25
cd5325f chore(auto): session dd58b43c 2026-03-25
e77469e feat: GitHub Models API investigation + wrapper (manual tier, pending benchmark)
769ebfe security: add tools restriction to 27 agents, disable MCP auto-approve
20d52bd feat: ECC optimizations — thinking tokens, haiku subagents, instinct evolution, compact hints
60a562f docs: add real next steps to handover 2026-03-25
d92968b feat(bloque9): smart relevance scoring + fact extraction (batch mode)
9d0805b feat(bloque9): hybrid search engine — vector + FTS5 keyword + graph RRF
99f75fd feat(bloque9): connect vector_store to pipeline — cosine KNN replaces JSON cosine
9a5323a feat(bloque9): temporal memory + sqlite-vec migration
fc4e7f7 security: fail-closed auth + expanded prompt injection sanitization
5ccf9fa security: fix C1 auto-report exposure, H1 telegram auth, H2 fail2ban, medium findings
f3ee5b0 fix: audit_trigger T2 calibration + error_log resolved = 84.6/100
527175f fix: audit_trigger fires auditor_local + Telegram on trigger; sqlite_mcp in .mcp.json
a886def feat: reactivate 5 dormant scripts — reconcile_errors, audit_trigger, sqlite_mcp, subscription, energy_tracker
4507a5e refactor: CLAUDE.md 159→67 lines, move inline content to rules/
1fbce8d chore: purge 19 dead/superseded scripts from archive, keep 6 dormant
6858909 chore: bash-safety rules, archive catalog
53e58c8 fix: orphan_finder scans .sh, rate_limiter archived, CLAUDE.md cleaned
05de3ab chore: document CLI tools, archive orphans, system cleanup
32a7617 chore: add orphan_finder.py + archive backfill_routing_feedback
b0adafa feat: stitch skills installed + benchmark v2 relaunched
86dbf6e feat: red-team v2 — pre-verification + external attack + anti-false-positive
3e7cff5 fix(security): defense-in-depth /cc command — 4 layer sanitization
b3d61ee feat: dual gold standard — Gemini silver + Sonnet gold
47ffa19 chore(auto): session fbe5df8c 2026-03-25
d6a2a2a feat: /red-team v2 — pre-report verification + external attack simulation
101038e fix(security): comprehensive blacklist multiline + shell operator blocking
1d43417 feat: dual gold standard — Gemini 2.5 Flash (silver) + Sonnet 4.6 (gold when available)
dd2dcf0 docs: add real next steps to handover 2026-03-25
e3c5f36 feat: enricher v2 — confidence gate 0.55, subdomain classifier, prompt structuring, CoT detection
68c5b72 fix(enricher): pre-benchmark cleanup — remove ambiguous distributed_systems keywords
f09f5e4 feat(enricher): subdomain role assignment in domain_lens + amplify Tier B
6a54f06 fix(enricher): remove bare 'kelly' false-positive keyword
2aa87d0 feat(enricher): subdomain classifier — 20+ subdomain keyword maps
5e11da6 fix(enricher): preserve chunk scores through amplify() pipeline, fix CoT guard
f098608 fix(enricher): integrate confidence gate into amplify() + CoT detection
4207c4a fix(enricher): rename _TIER_B_FLOOR→_MIN_SIM_FLOOR
14175d4 chore(auto): session 61471f44 2026-03-25
4972378 fix(enricher): raise confidence gate thresholds
5f33916 chore: nightly maintenance — 2026-03-25
56e0faa fix: benchmark uses Claude CLI for Sonnet gold standard + Telegram report
cc51a6e feat: benchmark system — 20 tasks x 5 runs x DQ ON/OFF vs Sonnet gold standard
9a5329f fix(security): resolve 6 medium/high findings from second red-team audit
bfa7c2b fix(security): resolve 6 medium findings from red-team audit
c979f71 fix(security): secure temp file creation with atomic write + restricted perms
ee1fa45 fix(security): case-insensitive blacklist + expanded blocked terms in /cc
53e0b83 fix(security): sanitize user input with shlex.quote in director.py
f7ca148 feat: adversarial security system — red-team + blue-team + iterative hardening cycle
```

**Total commits hoy:** 52 commits

---

## 14. ROADMAP TO 10/10

Sistema actual: **8/10**. Ver detalle completo en `docs/ROADMAP_TO_10.md`.

| Gap | Impacto | Esfuerzo | Prioridad |
|-----|---------|---------|-----------|
| F6. Feedback loop cerrado (rating Telegram→routing_feedback) | Alto | 3h | 1 |
| F4. Tests 200+ (coverage ~5% → 60%+) | Alto | 8h | 2 |
| F2. Misroute rate tracking (tier_used vs tier_optimal) | Medio | 2h | 3 |
| F5. /stats Telegram dashboard desde móvil | Medio | 2h | 4 |
| F1. ML Router RF entrenar con 9972 filas routing_feedback | Alto | 4h | 5 |
| F3. Cost tracking real (instrumentar llamadas LLM) | Medio | 2h | 6 |
| F9. Agent skill contracts (input/output schema) | Medio | 3h | 7 |
| F10. Re-benchmark cron trimestral | Bajo | 0.5h | 8 |
| F8. ADR documentation (10 decisiones clave) | Bajo | 2h | 9 |
| F7. jarvis rename completo | Bajo | 4h | 10 |

Ruta rápida 8→9/10: F6 + F2 + F5 = ~7h. Total a 10/10: ~31h.

---
*Checkpoint v1 — 2026-03-25 21:30 UTC | v2 — 2026-03-25 22:15 UTC — claude-sonnet-4-6*
