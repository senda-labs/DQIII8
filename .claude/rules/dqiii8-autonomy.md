# DQIII8 — Autonomous Execution

> Autonomy rules for VPS mode without continuous supervision.

- Bug reports: fix immediately. Point at logs/errors, resolve, verify. Zero hand-holding.
- If fix requires >3 files or touches architecture → enter plan mode first.
- Autonomous mode (VPS): execute plans with ≤5 steps and no destructive actions without asking.
- Destructive actions (delete, drop, force-push) or ambiguous intent → notify user, wait for confirmation.

## Relationship with common/development-workflow.md
The ECC workflow (Research → Plan → TDD → Review → Commit) is compatible.
DQIII8 adds: Telegram notification for critical decisions via jarvis_bot.
