# DQIII8 — Plan Maestro v2.0
Fecha: 2026-03-18 | Motor: Claude Sonnet 4.6 + Opus 4.6
Metáfora: Los modelos de IA son el motor del F1.
DQIII8 es la transmisión, aerodinámica, telemetría y estrategia
que convierte ese motor en victorias.

## Estado del sistema
Score: 86.0/100 | Sesiones: 150 | Fecha: 2026-03-18

## Bloques completados
- Bloque 0: Bootstrap VPS, estructura base ✅
- Bloque 1: Claude Code 2026 features, routing real ✅
- Bloque 2: Director v3, knowledge/ por agente, Agent Teams ✅
- Bloque 3: mem0, Shannon 10/10, contexts, security ✅
- Bloque 4: Auditor SPC, auto-researcher, sandbox ✅
- Bloque 5: Supervisor 3-layer, autonomous_loop.sh, bypassPermissions ✅

## Bloque 6 — En curso
Open source release: install.sh, README.md, CONTRIBUTING.md
Repo: github.com/senda-labs/DQIII8

## Bloque 4.5 — Pendiente (prioridad alta)
5 agentes de dominio del conocimiento humano:
- Norte (cabeza): Ciencias Formales — matemáticas, lógica, computación
- Este (derecha): Ciencias Naturales — física, química, biología
- Sur (pies): Ciencias Sociales — economía, finanzas, derecho
- Oeste (izquierda): Humanidades y Artes — literatura, filosofía, historia
- Centro (tronco): Ciencias Aplicadas — ingeniería, medicina, tecnología
Función: clasifican y amplían el prompt del usuario antes de
pasarlo al agente funcional. El usuario no necesita saber hacer prompts.

## Bloques pendientes
- **Bloque 4.6** — Modo sueño: ejecución programada de tareas de mantenimiento (auto-researcher, consolidación, cleanup)
- Bloque 7: UI/web (Codeman Respawn + CloudCLI plugins + push notifications)
- Bloque 8: Benchmark real 3 tiers
- Bloque 9: Graphiti temporal memory (reemplaza mem0 SQLite)
- Bloque 10: Knowledge passport entre proyectos

## Arquitectura actual
Motor: Claude Sonnet 4.6 / Opus 4.6 / Haiku 4.5
Tier 1: Ollama qwen2.5-coder:7b (local, $0)
Tier 2: Groq llama-3.3-70b + OpenRouter (cloud free, $0)
Tier 3: Claude API (paid, solo cuando necesario)
Supervisor: 3-layer (whitelist → LLM → Telegram)
Seguridad: Shannon semgrep score 10/10
Memoria: vault_memory SQLite + decay
Auto-mejora: SPC triggers + auto-researcher + sandbox tester
Obsidian: vault sincronizado via git en tiempo real

## Lo que DQIII8 hace que nadie más hace junto
1. Se audita a sí mismo con métricas reales (SPC)
2. Ruta automáticamente al modelo más barato que resuelve la tarea
3. Knowledge base por agente con embeddings
4. Auto-researcher que testea mejoras en sandbox antes de integrarlas
5. El usuario no necesita saber hacer prompts — el sistema amplifica
