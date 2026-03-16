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
| content-automation | obsidian-markdown, fal-ai-media |
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
| common/coding-style | ECC/affaan-m | ✅ APROBADA | No | Inmutabilidad, organización archivos |
| common/git-workflow | ECC/affaan-m | ✅ APROBADA (con override) | Leve | JARVIS NOTE aplicado: atribución Co-Authored-By activa |
| common/agents | ECC/affaan-m | ✅ APROBADA (con override) | **Sí** | Override aplicado: agentes JARVIS reemplazan tabla ECC |
| common/performance | ECC/affaan-m | ✅ APROBADA (con override) | **Sí** | Override aplicado: routing 3-tier JARVIS reemplaza Haiku/Sonnet/Opus |
| common/security | ECC/affaan-m | ✅ APROBADA | No | Compatible con jarvis-prohibitions |
| common/testing | ECC/affaan-m | ✅ APROBADA | No | 80% coverage, TDD |
| common/hooks | ECC/affaan-m | ✅ APROBADA | No | "no dangerously-skip-permissions" alineado con jarvis-prohibitions |
| common/patterns | ECC/affaan-m | ✅ APROBADA | No | Repository pattern, skeleton projects |
| common/development-workflow | ECC/affaan-m | ✅ APROBADA | No | Research→Plan→TDD→Review→Commit |
| python/coding-style | ECC/affaan-m | ✅ APROBADA | No | PEP8, type hints — ver jarvis-python para overrides |
| python/hooks | ECC/affaan-m | ✅ APROBADA | No | Black/ruff auto-format — compatible con PostToolUse JARVIS |
| python/patterns | ECC/affaan-m | ✅ APROBADA | No | Protocol, dataclasses, async |
| python/security | ECC/affaan-m | ✅ APROBADA | No | dotenv, KeyError si falta secret |
| python/testing | ECC/affaan-m | ✅ APROBADA | No | pytest, coverage |
| jarvis-prohibitions | JARVIS | ✅ APROBADA | — | Reglas absolutas JARVIS, máxima prioridad |
| jarvis-python | JARVIS | ✅ APROBADA | — | Black, pathlib, encoding, async |
| jarvis-autonomy | JARVIS | ✅ APROBADA | — | Modo VPS, acciones destructivas |
| jarvis-context-window | JARVIS | ✅ APROBADA | — | Green/Yellow/Orange/Red thresholds |

## Skills auto-generadas desde git history (2026-03-12)

| Skill | Fuente | Status | Aprobada por | Notas |
|-------|--------|--------|--------------|-------|
| jarvis-multi-provider-routing | git-analysis/jarvis (50 commits) | ✅ APROBADA | Iker | Patrón 3-tier routing: cuándo añadir providers, fallback chain, anti-patrones. Modelos Tier-2 corregidos (nemotron:free, qwen3:free) |
| jarvis-agent-creation | git-analysis/jarvis (50 commits) | ✅ APROBADA | Iker | Estructura canónica de agentes, modelo correcto por tier, archivos co-cambiados. data-analyst corregido a claude-sonnet-4-6 |
| continuous-learning-v2 | ECC/affaan-m (adaptado) | ✅ APROBADA | Iker | Instincts SQLite + stop.py integration + /instinct-status command |

## Skills P2a — ECC segunda revisión (2026-03-16)

| Skill | Fuente | Status | Aprobada por | Notas |
|-------|--------|--------|--------------|-------|
| security-review | ECC/affaan-m (adaptado Python/SQLite) | ✅ APROBADA | Iker | OWASP checklist JARVIS-adaptado: secrets, SQL injection, shell safety, hook safety |
| verification-loop | ECC/affaan-m (adaptado Black/pytest) | ✅ APROBADA | Iker | Pipeline post-código: black → ruff → mypy → pytest → security scan → diff |
| tdd-workflow | ECC/affaan-m (adaptado pytest) | ✅ APROBADA | Iker | TDD con pytest: RED→GREEN→REFACTOR, fixtures SQLite in-memory, smoke tests CLI |
| fal-ai-media | ECC/affaan-m (adaptado content-automation) | ✅ APROBADA | Iker | flux-general + negative_prompt + reference_image_url + Seedance video + costes |
| strategic-compact | ECC/affaan-m (adaptado JARVIS) | ✅ APROBADA | Iker | Compactar en boundaries lógicos, no mid-task; complementa jarvis-context-window.md |
| evolved/ssim | /evolve auto (4 instincts) | ✅ APROBADA | Iker | R1-R4: delta-injection prohibida, resolucion scorer exacta, anomalia >0.1 = hacking, lever estructural |
