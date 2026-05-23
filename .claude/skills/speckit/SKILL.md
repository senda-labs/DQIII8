---
name: speckit
description: Spec-Driven Development (SDD) con github/spec-kit. Úsalo para arrancar cualquier feature no trivial en un proyecto nuevo o existente. Cubre instalación, ciclo completo SDD y restricciones críticas del entorno dqiii8.
command: /speckit
allowed-tools: [Bash, Read, Write, Edit]
user-invocable: true
auto-invoke:
  - when: "Usuario describe una feature o proyecto nuevo de cierta envergadura (>3 ficheros, arquitectura propia)"
    action: "Sugerir /speckit para arrancar el ciclo SDD antes de implementar"
---

# /speckit — Spec-Driven Development con spec-kit

Metodología oficial para crear features nuevas en proyectos dqiii8.
Repositorio: **github.com/github/spec-kit** (v0.8.14+, MIT, 105K+ stars).

La idea central: el spec define el QUÉ y el POR QUÉ. El código sirve al spec, no al revés.

---

## Cuándo usar

- Feature nueva que toca ≥3 módulos o crea estructura propia
- Nuevo proyecto o sub-proyecto bajo `my-projects/`
- Decisión de arquitectura con múltiples opciones razonables

No usar para: hotfixes, cambios de 1-2 ficheros, tareas de mantenimiento.

---

## Instalación (primera vez en un proyecto)

### 1. Verificar que `uv` está disponible

```bash
source $HOME/.local/bin/env && uv --version
# Si no existe: curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Instalar specify-cli

```bash
source $HOME/.local/bin/env
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git
specify --version   # debe mostrar 0.8.x
```

### 3. Inicializar en el proyecto (desde su raíz)

```bash
cd my-projects/<nombre-proyecto>
echo "y" | specify init --here --integration claude
```

### 4. CRÍTICO — Borrar inmediatamente la extensión git

La extensión git de spec-kit viola las reglas inviolables de dqiii8:
auto-commit, git push, git init sin control humano.

```bash
# Borrar extensión y skills git
rm -rf .specify/extensions/git
rm -rf .claude/skills/speckit-git-{commit,feature,initialize,remote,validate}
rm -rf .claude/skills/speckit-taskstoissues

# Limpiar extensions.yml
cat > .specify/extensions.yml << 'EOF'
installed: []
settings:
  auto_execute_hooks: false
EOF

# Limpiar .registry
echo '{ "schema_version": "1.0", "extensions": {} }' > .specify/extensions/.registry
```

### 5. Actualizar el manifest del proyecto (si aplica INV-1)

Si el proyecto tiene `structure.manifest.yaml`, añadir los directorios de spec-kit
y eliminar los de la extensión git antes del primer commit.

---

## Ciclo SDD completo

Los skills de spec-kit quedan instalados en `.claude/skills/` del proyecto tras el `init`.
Se invocan directamente en la sesión Claude Code desde la raíz del proyecto.

### Paso 1 — Constitución (una sola vez por proyecto)

```
/speckit-constitution
```

Rellena `.specify/memory/constitution.md` con los principios del proyecto.
Lee el CLAUDE.md y la arquitectura existente antes de invocar.
Añadir tras el título:
> En cualquier conflicto estructural, el fichero de arquitectura sellado es la autoridad.

### Paso 2 — Especificación

```
/speckit-specify <descripción de la feature en lenguaje natural>
```

Crea `specs/<NNN>-<nombre>/spec.md` con:
- User Stories priorizadas (P1, P2, P3) con criterios de aceptación testables
- Functional Requirements (FR-NNN)
- Success Criteria tecnología-agnósticos
- Edge cases y asunciones

**Regla**: el spec no menciona lenguajes, frameworks ni APIs. Solo QUÉ y POR QUÉ.

### Paso 3 — Plan

```
/speckit-plan
```

Crea `specs/<NNN>/plan.md` + `research.md` + `data-model.md` + `contracts/`.
Aquí sí se decide el stack técnico, la estructura de ficheros y las interfaces.
Verifica que el plan no viola la arquitectura del proyecto antes de continuar.

### Paso 4 — Tareas

```
/speckit-tasks
```

Crea `specs/<NNN>/tasks.md` — lista de tareas ordenadas por dependencia.
Formato estricto: `- [ ] T001 [P] [US1] Descripción con ruta exacta`.
Identifica qué tareas son paralelizables.

### Paso 5 — Implementación

Implementar manualmente siguiendo `tasks.md`, tarea a tarea.
Marcar cada tarea completada en el fichero conforme avanza.
El skill `/speckit-implement` fue eliminado de los proyectos — implementar siempre con control humano.

---

## Estructura que genera spec-kit

```
.specify/
├── extensions.yml          # sin git extension tras limpieza
├── extensions/.registry    # vacío
├── feature.json            # puntero a la feature activa
├── memory/constitution.md  # principios del proyecto
├── scripts/bash/           # setup-plan.sh, setup-tasks.sh
├── templates/              # plantillas de spec/plan/tasks
└── workflows/speckit/      # workflow Full SDD Cycle

.claude/skills/             # skills instaladas por spec-kit
├── speckit-specify/
├── speckit-plan/
├── speckit-tasks/
├── speckit-analyze/        # opcional
├── speckit-checklist/      # opcional
└── speckit-clarify/        # opcional

specs/<NNN>-<nombre>/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── tasks.md
├── checklists/requirements.md
└── contracts/
```

---

## Restricciones dqiii8 al usar spec-kit

| Regla | Motivo |
|-------|--------|
| NO git extension | Auto-commits y push sin control humano — violación inviolable |
| NO speckit-taskstoissues | Crea issues en GitHub — interacción con remoto no autorizada |
| NO speckit-implement | Implementación siempre con control humano, no automatizada |
| Commits siempre manuales | Regla central de dqiii8: el humano aprieta el commit |
| NO --no-verify | Los hooks de pre-commit son la red de seguridad |

---

## Comandos de verificación post-instalación

```bash
specify --version                          # 0.8.x
ls .claude/skills/                         # solo speckit-{specify,plan,tasks,...} + propios
ls .specify/extensions/git 2>/dev/null || echo "git extension limpia ✓"
cat .specify/extensions.yml                # installed: [], auto_execute_hooks: false
```

---

## Referencia rápida

```bash
# Instalar specify-cli (si no está)
source $HOME/.local/bin/env && uv tool install specify-cli --from git+https://github.com/github/spec-kit.git

# Inicializar proyecto (responde y a la pregunta de directorio no vacío)
echo "y" | specify init --here --integration claude

# Después del init, SIEMPRE limpiar git extension (ver paso 4 arriba)

# Ciclo en Claude Code (dentro del proyecto):
/speckit-constitution   # una vez
/speckit-specify <descripción>
/speckit-plan
/speckit-tasks
# luego implementar manualmente siguiendo tasks.md
```

---

## Ejemplo de referencia

Primer uso completo: `my-projects/pokemon-genesis-chaos`, feature `001-tileforge-saas`.
Spec completo en `specs/001-tileforge-saas/` — consultar como plantilla de calidad.
