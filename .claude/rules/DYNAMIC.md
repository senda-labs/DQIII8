# DQIII8 — Dynamic Rules (RAG)

## REGLA UNIVERSAL — API KEY Y OAUTH

PROHIBIDO modificar o exportar ANTHROPIC_API_KEY en producción.
Siempre OAuth (Claude Max). Subprocess: env={"ANTHROPIC_API_KEY": ""}
Si "Credit balance too low": verificar que ANTHROPIC_API_KEY="" en subprocess.

Rules contextuales inyectadas por rules_dispatcher.py (llamado desde pre_tool_use.py) — nunca
el registro entero. Rango canónico: 1060–8117 tokens; suelo de sesión 2807. Mecanismo completo,
re-medición y qué cuenta como suelo/techo: SSOT es el docstring de rules_dispatcher.py; ver
también 02_hooks_and_permissions.md §Rules Dispatcher.
PROHIBIDO: episodic-memory (consume 48K tokens sin valor).
Estado empresa: python3 -m core.cli status --slug {SLUG}

## SPEC-KIT / SDD (nuevo proyecto o feature)

Skill: `/speckit` — leer antes de arrancar cualquier feature no trivial.
Instalación: `source $HOME/.local/bin/env && uv tool install specify-cli --from git+https://github.com/github/spec-kit.git`
Init: `echo "y" | specify init --here --integration claude`
CRÍTICO post-init: borrar `.specify/extensions/git/` + skills `speckit-git-*` + `speckit-taskstoissues`
Ciclo: `/speckit-constitution` → `/speckit-specify` → `/speckit-plan` → `/speckit-tasks` → implementar manualmente
Referencia: `my-projects/pokemon-genesis-chaos/specs/001-tileforge-saas/`

