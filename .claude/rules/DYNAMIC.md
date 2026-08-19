# DQIII8 — Dynamic Rules (RAG)

## REGLA UNIVERSAL — API KEY Y OAUTH

PROHIBIDO modificar o exportar ANTHROPIC_API_KEY en producción.
Siempre OAuth (Claude Max). Subprocess: env={"ANTHROPIC_API_KEY": ""}
Si "Credit balance too low": verificar que ANTHROPIC_API_KEY="" en subprocess.

Rules contextuales inyectadas por rules_dispatcher.py (llamado desde pre_tool_use.py).
Mecanismo: tool_name + tool_input → alias → carga un subconjunto del registro, con ficheros de .claude/rules_db/ y de .claude/rules/ (mínimo: 2 ficheros = solo _ALWAYS; máximo alcanzable: 13 ficheros, un Bash que dispara todas las keywords; un `git status` ya inyecta 4). En tokens: ~1060–7959 tokens, cl100k_base real, re-medido 2026-08-19; techo = máximo realmente alcanzable, no el peor caso de la matriz.
NUNCA carga el registro entero en un mismo turno (recuento vivo: `len(_REGISTRY)` en rules_dispatcher.py; el subtotal de rules_db/ está fijado y validado en CLAUDE.md). Ver 02_hooks_and_permissions.md §Rules Dispatcher.
PROHIBIDO: episodic-memory (consume 48K tokens sin valor).
Estado empresa: python3 -m core.cli status --slug {SLUG}

## SPEC-KIT / SDD (nuevo proyecto o feature)

Skill: `/speckit` — leer antes de arrancar cualquier feature no trivial.
Instalación: `source $HOME/.local/bin/env && uv tool install specify-cli --from git+https://github.com/github/spec-kit.git`
Init: `echo "y" | specify init --here --integration claude`
CRÍTICO post-init: borrar `.specify/extensions/git/` + skills `speckit-git-*` + `speckit-taskstoissues`
Ciclo: `/speckit-constitution` → `/speckit-specify` → `/speckit-plan` → `/speckit-tasks` → implementar manualmente
Referencia: `my-projects/pokemon-genesis-chaos/specs/001-tileforge-saas/`

