# Skills Registry — INDEX

## Fuentes activas
- `cache/obsidian-skills/` → kepano/obsidian-skills (clonado 2026-03-12)
- `custom/` → skills aprobadas y listas para uso en producción

## Estado de revisión

| Skill | Fuente | Status | Aprobada por | Notas |
|-------|--------|--------|--------------|-------|
| obsidian-markdown | kepano/obsidian-skills | ✅ APROBADA | Iker | Sintaxis correcta para vault Obsidian — usar en todos los .md |
| obsidian-bases | kepano/obsidian-skills | ✅ APROBADA | Iker | Queries tipo SQL sobre notas Obsidian |
| defuddle | kepano/obsidian-skills | ✅ APROBADA | Iker | Extracción limpia de contenido web |
| obsidian-cli | kepano/obsidian-skills | ❌ RECHAZADA | Iker | Inútil en VPS sin interfaz gráfica |
| json-canvas | kepano/obsidian-skills | ⏸ APLAZADA | Iker | Canvas interactivo — aplazado para fase posterior |

## Combos activos

| Proyecto | Skills cargadas |
|----------|----------------|
| jarvis-core | obsidian-markdown, obsidian-bases |
| content-automation | obsidian-markdown |
| hult-finance | obsidian-markdown, defuddle |
| leyendas-del-este | obsidian-markdown |

## Regla de carga
Solo skills con estado ✅ APROBADA pueden añadirse a un combo.
Proceso: cache/ → revisión Iker → revisión Claude → APROBADA → custom/ → INDEX.

## Paths
- Cache: `skills-registry/cache/obsidian-skills/skills/`
- Custom (producción): `skills-registry/custom/`

## Rules integradas (ECC + JARVIS)

| Rule | Fuente | Status | Conflicto | Notas |
|------|--------|--------|-----------|-------|
| common/coding-style | ECC/affaan-m | ⏸ PENDIENTE_REVISION | No | Inmutabilidad, organización archivos |
| common/git-workflow | ECC/affaan-m | ⏸ PENDIENTE_REVISION | Leve | Ver nota JARVIS override (atribución commits) |
| common/agents | ECC/affaan-m | ⏸ PENDIENTE_REVISION | **Sí** | Agentes ECC != JARVIS agents. Override aplicado |
| common/performance | ECC/affaan-m | ⏸ PENDIENTE_REVISION | **Sí** | Model routing ECC != JARVIS 3-tier. Override aplicado |
| common/security | ECC/affaan-m | ⏸ PENDIENTE_REVISION | No | Compatible con jarvis-prohibitions |
| common/testing | ECC/affaan-m | ⏸ PENDIENTE_REVISION | No | 80% coverage, TDD |
| common/hooks | ECC/affaan-m | ⏸ PENDIENTE_REVISION | Leve | "no dangerously-skip-permissions" — JARVIS lo usa solo en bot |
| common/patterns | ECC/affaan-m | ⏸ PENDIENTE_REVISION | No | Repository pattern, skeleton projects |
| common/development-workflow | ECC/affaan-m | ⏸ PENDIENTE_REVISION | No | Research→Plan→TDD→Review→Commit |
| python/coding-style | ECC/affaan-m | ⏸ PENDIENTE_REVISION | No | PEP8, type hints — ver jarvis-python para overrides |
| python/hooks | ECC/affaan-m | ⏸ PENDIENTE_REVISION | No | Black/ruff auto-format — compatible con PostToolUse JARVIS |
| python/patterns | ECC/affaan-m | ⏸ PENDIENTE_REVISION | No | Protocol, dataclasses, async |
| python/security | ECC/affaan-m | ⏸ PENDIENTE_REVISION | No | dotenv, KeyError si falta secret |
| python/testing | ECC/affaan-m | ⏸ PENDIENTE_REVISION | No | pytest, coverage |
| jarvis-prohibitions | JARVIS | ✅ APROBADA | — | Reglas absolutas JARVIS, máxima prioridad |
| jarvis-python | JARVIS | ✅ APROBADA | — | Black, pathlib, encoding, async |
| jarvis-autonomy | JARVIS | ✅ APROBADA | — | Modo VPS, acciones destructivas |
| jarvis-context-window | JARVIS | ✅ APROBADA | — | Green/Yellow/Orange/Red thresholds |

## Skills auto-generadas desde git history (2026-03-12)

| Skill | Fuente | Status | Aprobada por | Notas |
|-------|--------|--------|--------------|-------|
| jarvis-multi-provider-routing | git-analysis/jarvis (50 commits) | ⏸ PENDIENTE_REVISION | — | Patrón 3-tier routing: cuándo añadir providers, fallback chain, anti-patrones |
| jarvis-agent-creation | git-analysis/jarvis (50 commits) | ⏸ PENDIENTE_REVISION | — | Estructura canónica de agentes, modelo correcto por tier, archivos co-cambiados |
