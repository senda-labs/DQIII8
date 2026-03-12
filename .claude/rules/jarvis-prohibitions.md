# JARVIS — Prohibiciones (NEVER)

> Reglas absolutas del sistema. Prioridad máxima sobre cualquier otra rule.

- NEVER write to .env, secrets, API keys, or any credential file.
- NEVER modify .claude/settings.json, CLAUDE.md, or database/schema.sql without explicit user request.
- NEVER delete data from jarvis_metrics.db.
- NEVER force-push, rebase main, or delete branches without user confirmation.
- NEVER load a skill from skills-registry/cache/ that hasn't been reviewed (check INDEX.md status).
- NEVER keep pushing when something breaks. STOP → re-plan → ask if uncertain.
- NEVER exceed 3 files modified without entering plan mode.
