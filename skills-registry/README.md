# skills-registry/

This directory stores Claude Code skills for DQIII8.

## Structure

```
skills-registry/
├── custom/          # Your custom skills (committed to your fork/workspace)
│   └── evolved/     # Auto-generated skills from session patterns
├── cache/           # Downloaded skills (gitignored — re-downloaded on demand)
└── INDEX.md         # Registry of all skills with status
```

## Creating a skill

A skill is a Markdown file with a specific format:

```markdown
---
name: my-skill
description: What this skill does and when to invoke it
---

## Instructions

[Skill content here]
```

Place your skill in `skills-registry/custom/my-skill.md` and add an entry to `INDEX.md`.

## Loading skills

Skills in `cache/` are loaded only if their status in `INDEX.md` is `ACTIVE`.
Never load skills with status `PENDIENTE_REVISION` or `DEPRECATED`.

```bash
# Invoke a skill from Claude Code
/my-skill
```

## Workspace skills

Personal skills (specific to your projects) should go in your workspace:
`dqiii8-workspace/skills-registry/custom/`

and be linked via `overlay.sh` if needed.
