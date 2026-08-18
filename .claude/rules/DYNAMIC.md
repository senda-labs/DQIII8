# DQIII8 — Dynamic Rules (RAG)

## REGLA UNIVERSAL — API KEY Y OAUTH

PROHIBIDO modificar o exportar ANTHROPIC_API_KEY en producción.
Siempre OAuth (Claude Max). Subprocess: env={"ANTHROPIC_API_KEY": ""}
Si "Credit balance too low": verificar que ANTHROPIC_API_KEY="" en subprocess.

Rules contextuales inyectadas por rules_dispatcher.py (llamado desde pre_tool_use.py).
Mecanismo: tool_name + tool_input → alias → carga 1-3 archivos de .claude/rules_db/ (~1.432–4.469 tokens, medido 2026-08-17).
NUNCA carga los 20+ archivos completos en un mismo turno. Ver 02_hooks_and_permissions.md §Rules Dispatcher.
PROHIBIDO: episodic-memory (consume 48K tokens sin valor).
Estado empresa: python3 -m core.cli status --slug {SLUG}

## SPEC-KIT / SDD (nuevo proyecto o feature)

Skill: `/speckit` — leer antes de arrancar cualquier feature no trivial.
Instalación: `source $HOME/.local/bin/env && uv tool install specify-cli --from git+https://github.com/github/spec-kit.git`
Init: `echo "y" | specify init --here --integration claude`
CRÍTICO post-init: borrar `.specify/extensions/git/` + skills `speckit-git-*` + `speckit-taskstoissues`
Ciclo: `/speckit-constitution` → `/speckit-specify` → `/speckit-plan` → `/speckit-tasks` → implementar manualmente
Referencia: `my-projects/pokemon-genesis-chaos/specs/001-tileforge-saas/`

