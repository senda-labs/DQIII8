---
name: skill-create
description: Analiza el historial git de JARVIS (y content-automation-faceless) para extraer patrones y generar SKILL.md en skills-registry/custom/. Versión adaptada de ECC skill-create para el ecosistema JARVIS.
allowed_tools: ["Bash", "Read", "Write", "Grep", "Glob"]
---

# /skill-create — Generación de Skills desde Git History

Analiza los repositorios de Iker para extraer patrones reales y generar skills
reutilizables en `skills-registry/custom/`.

## Uso

```
/skill-create                        # Analiza /root/jarvis (últimos 50 commits)
/skill-create --commits 100          # Más commits
/skill-create --repo content         # Analiza /root/content-automation-faceless
/skill-create --repo all             # Analiza ambos repos
/skill-create --instincts            # También genera instincts para continuous-learning-v2
```

## Qué hace

1. **Parsea el historial git** — commits reales, archivos cambiados, frecuencia de co-cambio
2. **Filtra ruido** — excluye: merge commits, "session handover", "gemini review", "auto-commit", stop hook
3. **Detecta patrones** — workflows repetidos, arquitectura, convenciones
4. **Genera SKILL.md** — compatible con INDEX.md de JARVIS
5. **Actualiza INDEX.md** — añade la skill con estado PENDIENTE_REVISION

## Pasos de análisis

### Paso 1: Recopilar datos git

```bash
REPO=${REPO:-/root/jarvis}
cd $REPO

# Commits significativos (excluir ruido)
git log --oneline -${COMMITS:-50} --no-merges \
  --pretty=format:"%H|%s|%ad" --date=short \
  | grep -v "session handover\|gemini review\|auto-commit\|chore(review)"

# Archivos que más cambian juntos
git log --oneline -${COMMITS:-50} --name-only --pretty=format:"%s" \
  | grep -v "session handover\|gemini review\|^$\|^[a-f0-9]" \
  | sort | uniq -c | sort -rn | head -20

# Tipos de commit
git log --oneline -${COMMITS:-50} --no-merges \
  | grep -v "session handover\|gemini review" \
  | cut -d' ' -f2- | sed 's/:.*$//' | sort | uniq -c | sort -rn
```

### Paso 2: Detectar patrones

| Patrón | Señal de detección |
|--------|--------------------|
| **Routing multi-provider** | Cambios en `bin/*_wrapper.py` + CLAUDE.md juntos |
| **Creación de agentes** | Cambios en `.claude/agents/*.md` (2+ archivos a la vez) |
| **JAL workflow** | Cambios en `bin/jal_*.py` (4 archivos coordinados) |
| **Hooks lifecycle** | Cambios en `.claude/hooks/` + `bin/` juntos |
| **Commit conventions** | Prefijos feat/fix/chore/docs con emoji o sin él |
| **Session patterns** | Frecuencia y estructura de sessions/ |

### Paso 3: Generar SKILL.md

Output en `skills-registry/custom/{skill-name}/SKILL.md`:

```markdown
---
name: {skill-name}
version: 1.0.0
source: git-analysis/{repo-name}
analyzed_commits: {count}
analyzed_date: {YYYY-MM-DD}
repos: [/root/jarvis, /root/content-automation-faceless]  # según aplique
---

# {Skill Name}

## Patrón detectado
{descripción del patrón con evidencia del historial}

## Cuándo usar esta skill
{triggers específicos}

## Workflow
{pasos concretos con ejemplos reales del repo}

## Archivos involucrados
{lista de archivos típicamente tocados}

## Ejemplos del historial
{commits reales como evidencia}

## Anti-patrones
{qué evitar, basado en commits de fix:}
```

### Paso 4: Actualizar INDEX.md

Añadir a `skills-registry/INDEX.md`:

```markdown
| {skill-name} | git-analysis/{repo} | ⏸ PENDIENTE_REVISION | — | {descripción} |
```

Columnas requeridas por JARVIS: `Skill | Fuente | Status | Aprobada por | Notas`

### Paso 5 (opcional): Generar instincts

Si `--instincts`, crear también `skills-registry/custom/{skill-name}/instinct.yaml`:

```yaml
---
id: {repo}-{pattern-id}
trigger: "{cuándo aplica}"
confidence: 0.8
domain: {git|python|routing|agents}
source: git-analysis/{repo}
evidence_commits: {count}
---

# {Instinct Name}

## Action
{qué hacer}

## Evidence
- Analizado: {n} commits en {repo}
- Frecuencia: {percentage}% de feat commits siguen este patrón
```

## Repos analizados

| Repo | Path | Foco |
|------|------|------|
| jarvis | `/root/jarvis` | Infraestructura, agentes, JAL, routing |
| content-automation | `/root/content-automation-faceless` | Pipeline media, TTS, video |

## Output esperado

```
skills-registry/custom/
├── jarvis-multi-provider-routing/
│   └── SKILL.md
├── jarvis-agent-creation/
│   └── SKILL.md
└── {nombre-detectado}/
    ├── SKILL.md
    └── instinct.yaml  # si --instincts
```

## Notas JARVIS

- Output: `skills-registry/custom/` (NO `~/.claude/skills/`)
- Status inicial siempre: `⏸ PENDIENTE_REVISION`
- Para aprobar: Iker revisa → `✅ APROBADA` → añadir a combo en INDEX.md
- Prohibición: no cargar skills de `cache/` sin revisión (ver jarvis-prohibitions.md)

---
*Adaptado de ECC /skill-create para JARVIS — ver /tmp/ecc/commands/skill-create.md para original*
