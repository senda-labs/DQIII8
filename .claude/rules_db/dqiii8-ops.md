# DQIII8 — Operations & Prohibitions

**Autonomous mode (VPS)**: escalera de autonomía → `00_core_behavior.md` §Autonomous Execution Rules (siempre co-inyectado). Notificar al usuario por Telegram (dqiii8_bot).

**Absolute NEVER** (no user-request carve-out — see blocked-paths list in `02_hooks_and_permissions.md`, don't duplicate it here):
- Write to `.env` / secrets / credential files, or any path in that blocked-paths list.
- Delete data from `dqiii8.db`.
- Force-push, rebase main, or delete branches without user confirmation.
- Load a skill from `skills-registry/cache/` without checking `INDEX.md` status.
- Keep going after something breaks — STOP → re-plan → ask if uncertain.

**CLAUDE.md**: ≤100 lines, quick-reference map only. Details go in `docs/CHECKPOINT_*.md` / `PROJECT.md`.
