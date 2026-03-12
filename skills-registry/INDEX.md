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
