---
name: skill-create
description: Analyzes DQIII8 git history to extract patterns and generate SKILL.md files in skills-registry/custom/
command: /skill-create
allowed-tools: [Bash, Read, Write, Grep, Glob]
user-invocable: true
---

# /skill-create — Skill Generation from Git History

Analyzes DQIII8 repositories to extract real patterns and generate reusable skills.

## Usage
/skill-create
/skill-create --commits 100
/skill-create --repo <path>
/skill-create --instincts

## What it does
1. Parses git history — real commits, changed files, co-change frequency
2. Filters noise — excludes merge commits, handover, auto-commit
3. Detects patterns — repeated workflows, architecture, conventions
4. Generates SKILL.md — compatible with DQIII8 INDEX.md
5. Updates INDEX.md — adds the skill with status PENDING_REVIEW

## Output
Skills go to skills-registry/custom/{skill-name}/SKILL.md
Initial status: PENDING_REVIEW
To approve: review → APPROVED → add to INDEX.md combo

## Notes
- Output is skills-registry/custom/ — not .claude/skills/
- Do not load from cache/ without review
