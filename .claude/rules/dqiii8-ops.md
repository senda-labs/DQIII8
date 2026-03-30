# DQIII8 — Operations & Prohibitions

## Autonomous execution rules (VPS mode)
- Bug reports: fix immediately — point at logs, resolve, verify. Zero hand-holding.
- Fix requires >3 files or touches architecture → plan mode first
- Plans ≤5 steps + no destructive actions → execute autonomously
- Destructive/ambiguous → notify user, wait for confirmation
- Telegram notification for critical decisions via dqiii8_bot

## NEVER (absolute — highest priority)
- NEVER write to `.env`, secrets, API keys, or credential files
- NEVER modify `.claude/settings.json`, `CLAUDE.md`, or `database/schema.sql` without explicit user request
- NEVER delete data from `dqiii8.db`
- NEVER force-push, rebase main, or delete branches without user confirmation
- NEVER load a skill from `skills-registry/cache/` without checking INDEX.md status
- NEVER keep pushing when something breaks — STOP → re-plan → ask if uncertain
- NEVER exceed 3 files modified without entering plan mode

## CLAUDE.md size limit
CLAUDE.md must NEVER exceed 100 lines. It is a quick-reference map, not documentation.
Detailed docs belong in `docs/CHECKPOINT_*.md` or `PROJECT.md` files.
