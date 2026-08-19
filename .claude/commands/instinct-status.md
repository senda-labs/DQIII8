---
name: instinct-status
description: Shows learned instincts from dqiii8.db, grouped by project and confidence. Internal diagnostic tool — not for user invocation.
allowed-tools: [Bash]
---

# /instinct-status — Instinct Status

> **SSOT: `.claude/skills/instinct-status/SKILL.md`.** This command file is a
> pointer only — read the skill for the query, the ASCII output format and the
> notes. It previously carried a duplicate copy that declared the frontmatter key
> `allowed_tools` (underscore — a key no runtime reads), described the tool as
> user-facing where the skill declares `user-invocable: false`, and rendered the
> confidence bar with Unicode blocks where the skill uses ASCII. Reconciled
> 2026-08-18 (F2); the skill is the only place the procedure lives.
