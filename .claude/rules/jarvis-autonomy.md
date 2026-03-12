# JARVIS — Ejecución Autónoma

> Reglas de autonomía para modo VPS sin supervisión continua.

- Bug reports: fix immediately. Point at logs/errors, resolve, verify. Zero hand-holding.
- If fix requires >3 files or touches architecture → enter plan mode first.
- Autonomous mode (VPS): execute plans with ≤5 steps and no destructive actions without asking.
- Destructive actions (delete, drop, force-push) or ambiguous intent → notify user, wait for confirmation.

## Relación con common/development-workflow.md
El workflow de ECC (Research → Plan → TDD → Review → Commit) es compatible.
JARVIS añade: notificación Telegram en decisiones críticas vía jarvis_bot.
