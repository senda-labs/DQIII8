# /checkpoint — Save and Verify Session State

> **SSOT: `.claude/skills/checkpoint/SKILL.md`.** This command file is a pointer
> only — read the skill for `create` / `verify` / `list`, their arguments and the
> report formats. It previously carried a duplicate copy that omitted the
> `[ -f .claude/checkpoints.log ] || touch .claude/checkpoints.log` guard, so
> `verify` and `list` failed on a fresh install. Reconciled 2026-08-18 (F2).
