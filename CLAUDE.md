# DQIII8 — Working Charter

Autonomous AI orchestration engine (VPS, SSH-only). Enfoque, metodología y exigencias viven
aquí. Estado del sistema (DBs, excepciones puntuales, backups) vive en `docs/ARCHITECTURE.md`.
Comportamiento base siempre cargado: `.claude/rules/00_core_behavior.md` — este fichero no lo
repite, solo añade lo que ese no cubre.

## Enfoque — Enterprise-Grade Bar
- Verifica el artefacto final real (servicio desplegado, respuesta de API, DOCX entregable, fila
  de DB) — tests y logs no cuentan como verificación.
- Si algo no se pudo verificar (p.ej. UI sin navegador disponible), dilo explícitamente. Nunca
  reportes éxito sin haberlo comprobado.
- El listón es corrección verificada, no volumen: no autoriza a exceder el alcance pedido
  (Priority Ladder, `00_core_behavior.md`).
- Un error que se repite exige una comprobación estructural que bloquee la entrega hasta
  resolverse — no un parche puntual.

## Metodología — lo que no cubre 00_core_behavior.md
- Una ronda de aclaración afilada vale más que varios ciclos de corrección: si el prompt no fija
  objetivo + alcance + listón de "hecho", pregunta antes de iterar.
- Feature nueva no trivial → `/speckit` antes de entrar en modo plan (`.claude/rules_db/dqiii8-speckit.md`).
- Cost-first: el tier más barato capaz. Estado vigente de qué proveedor está operativo hoy no se
  fija aquí (cambia) — `00_core_behavior.md` § REGLA NIM es la SSOT siempre cargada.

## Protocolos de ejecución
- Plan ≤5 pasos, sin acciones destructivas → ejecuta autónomo, notifica después.
- Plan toca ≥3 módulos O alcance ambiguo → modo plan primero, espera confirmación, luego
  `/panel-review <plan-file>` (veredicto asesor, no gate — consume la única escalada a Opus por
  tarea; SSOT `.claude/skills/panel-review/`).
- Escritura en corpus de gobernanza (`.claude/{hooks,rules,rules_db,agents,skills}/`) →
  ESCALATE, espera confirmación humana antes de proceder.
- Un DENY del PermissionAnalyzer es final: no reintentes, no reordenes, no `--no-verify`/
  `--force`. Reconduce o pide al humano — nunca lo bordees.
- Acción destructiva/irreversible (DROP, cambio de schema en vivo, `rm -rf` de datos) → STOP,
  avisa, espera. Excepciones ya cerradas en código (SSOT `.claude/rules/02_hooks_and_permissions.md`):
  `rm -rf` de build/cache auto-aprobado; `git push --force` denegado sin excepción.
- Bug en producción → arréglalo ya: lee logs, aísla la causa, resuelve, verifica. Sin escoltas.

## Exigencias no negociables (Inviolable Rules)
- NUNCA escribas en `.env` ni en `CLAUDE.md` — ambos son blocked paths, sin excepción, ni
  siquiera edición manual directa. SSOT `.claude/rules/02_hooks_and_permissions.md` § Blocked paths.
- NUNCA hardcodees API keys — siempre `os.environ.get("VAR")`.
- NUNCA commitees `*.db` — gitignored por diseño. `database/schema_v2.sql` para instalaciones
  nuevas.
- `ANTHROPIC_API_KEY` = `""` en el env de todo subprocess al usar Claude Code OAuth — convención
  de operador, sin enforcement en código; si "Credit balance too low", verifica esto a mano
  primero.
- `database/schema_v2.sql` es la SSOT del schema — solo cambios aditivos vía migraciones
  revisadas; cambios destructivos de schema se señalan, nunca se ejecutan.
- `git push --force` — DENY absoluto en cualquier remote, ninguna confirmación lo desbloquea.

## Rule Engine — dónde mirar antes de actuar

| Dominio | Leer primero |
|---|---|
| Cualquier acción | `.claude/rules/00_core_behavior.md` (siempre cargado) |
| Estado del sistema (DBs, contadores, excepciones, backups) | `docs/ARCHITECTURE.md` |
| DB schema / SQL / sqlite3 | `.claude/rules/01_database_mutations.md` |
| Hooks o PermissionAnalyzer | `.claude/rules/02_hooks_and_permissions.md` |
| Tiering / routing / cambios de agente | `.claude/rules/03_tiering_and_routing.md` |
| Gate a Opus (cuándo escala una tarea) | `.claude/rules_db/dqiii8-plan-gate.md` |
| Feature nueva / SDD | `.claude/rules_db/dqiii8-speckit.md` |
| Delegación a agentes / qué nombres existen | `.claude/rules_db/common/agents.md` § Two runtimes, two SSOTs |
| Git / Bash safety | `.claude/rules_db/git-safety.md` |
| Prevención de errores recurrentes | `.claude/rules_db/dqiii8-error-prevention.md` |
| Pipeline intl-reports | `my-projects/intl-reports/RULE` |

## System Map (contadores — validator-enforced, no mover de aquí)
Hooks (15): `.claude/hooks/` | Skills (25): `.claude/skills/` | Agents (17): `.claude/agents/`
Contextual rules (12): `.claude/rules_db/` — 2 files minimum (`_ALWAYS`), 14 in the reachable ceiling case,
drawn from both `.claude/rules_db/` and `.claude/rules/` (`.claude/rules/02_hooks_and_permissions.md`).
Counts validator-enforced by `check_claude_md_counts()` in `bin/tools/validate_rules_registry.py`.
