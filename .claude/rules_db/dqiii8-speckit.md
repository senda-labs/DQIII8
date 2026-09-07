# DQIII8 — SPEC-KIT / SDD (nuevo proyecto o feature)

Skill: `/speckit` — leer antes de arrancar cualquier feature no trivial.
Instalación: `source $HOME/.local/bin/env && uv tool install specify-cli --from git+https://github.com/github/spec-kit.git`
Init: `echo "y" | specify init --here --integration claude`
CRÍTICO post-init: borrar `.specify/extensions/git/` + skills `speckit-git-*` + `speckit-taskstoissues`
Ciclo: `/speckit-constitution` → `/speckit-specify` → `/speckit-plan` → `/speckit-tasks` → implementar manualmente
Referencia: `my-projects/pokemon-genesis-chaos/specs/001-tileforge-saas/`
