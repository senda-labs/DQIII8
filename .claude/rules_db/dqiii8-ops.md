# DQIII8 — Operations & Prohibitions

**Autonomous mode (VPS)**: bugs → fix now (logs → isolate → resolve → verify, no hand-holding). Plans ≤5 steps + non-destructive → run autonomously. Plan touches >3 files or architecture → plan mode first. Destructive/ambiguous → notify user via Telegram (dqiii8_bot), wait.

**Absolute NEVER** (no user-request carve-out — see blocked-paths list in `02_hooks_and_permissions.md`, don't duplicate it here):
- Write to `.env` / secrets / credential files, or any path in that blocked-paths list.
- Delete data from `dqiii8.db`.
- Force-push, rebase main, or delete branches without user confirmation.
- Load a skill from `skills-registry/cache/` without checking `INDEX.md` status.
- Keep going after something breaks — STOP → re-plan → ask if uncertain.

**CLAUDE.md**: ≤100 lines, quick-reference map only. Details go in `docs/CHECKPOINT_*.md` / `PROJECT.md`.
