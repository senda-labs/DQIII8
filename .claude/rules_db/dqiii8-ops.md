# DQIII8 — Operations & Prohibitions

**Autonomous mode (VPS)**: escalera de autonomía → `00_core_behavior.md` §Autonomous Execution Rules (siempre co-inyectado). Notificar al usuario por Telegram (dqiii8_bot).

**Absolute NEVER** (no user-request carve-out — see blocked-paths list in `02_hooks_and_permissions.md`, don't duplicate it here):
- Write to `.env` / secrets / credential files, or any path in that blocked-paths list.
- Delete data from `dqiii8.db`.
- Rebase main or delete branches without user confirmation. (`git push --force` is stricter: DENY
  since 2026-08-18, confirmation does not unblock it — SSOT `git-safety.md`.)
- Load a skill from `skills-registry/cache/` without checking `INDEX.md` status.
- Keep going after something breaks — STOP → re-plan → ask if uncertain.

**CLAUDE.md**: ≤100 lines, quick-reference map, blocked-path (solo humano). Detalle → `my-projects/<proyecto>/PROJECT.md`, `sessions/*.md`, `.claude/checkpoints.log`.

**API KEY y OAuth (universal)**: PROHIBIDO modificar o exportar `ANTHROPIC_API_KEY` en
producción. Siempre OAuth (Claude Max). Subprocess: `env={"ANTHROPIC_API_KEY": ""}`. Convención
de operador, no invariante forzada por código (`dispatch.py`/`director.py` no tocan esta var).
Si "Credit balance too low": verificar a mano que `ANTHROPIC_API_KEY=""` en el subprocess antes
de nada más. PROHIBIDO: episodic-memory (consume 48K tokens sin valor). Estado de una empresa:
`python3 -m core.cli status --slug {SLUG}`.
