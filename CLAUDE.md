nano /root/dqiii8/CLAUDE.md
```

Contenido completo — copia esto y pégalo dentro de nano:
```
# DQIII8 — System Identity

Autonomous AI orchestration on VPS (Ubuntu, SSH-only).
Routes queries through multi-tier LLM pipeline with domain knowledge enrichment.
Primary UI: Telegram bot (@JARVISCONTROL3BOT).

## Architecture
- Entry: Telegram /cc > domain_classifier > agent_selector > knowledge_enricher > LLM
- Tiers: C (ollama/qwen2.5-coder:7b) > B (groq/llama-3.3-70b) > A (anthropic/sonnet-4.6) > S (opus-4.6)
- Fallback: C>B>A with auto-escalation if domain != applied_sciences
- DB: SQLite (dqiii8.db + dqiii8_metrics.db), 79 tables
- Hooks: 12 lifecycle hooks (.claude/hooks/)
- Skills: 17 slash commands (.claude/skills/)
- Agents: 9 active + 18 archived (.claude/agents/, _archived/)

## Key Files
- bin/core/openrouter_wrapper.py - DQ pipeline + model routing + tier costs
- bin/ui/dqiii8_bot.py - Telegram bot
- bin/director.py - Autonomous mode orchestrator
- bin/j.sh - CLI entry point (j cc, j loop, j status)
- .claude/hooks/pre_tool_use.py - PermissionAnalyzer v5
- .claude/hooks/session_start.py - Context injection
- .claude/hooks/stop.py - Session close + auto-commit + lessons
- config/domain_agent_map.json - Agent routing map (5 domains)
- database/schema_v2.sql - DB schema (idempotent)
- tasks/lessons.md - Learned lessons (append-only)
- knowledge/ - 5 domain indexes (bge-m3, 1024d)
- RULE - Project directives (always read at session start)

## System Checkpoints
docs/CHECKPOINT_*.md contains full system context (architecture, DB schema, agents, metrics).
Checkpoints MAY BE OUTDATED. Before relying on one, quick-verify:
  python3 -m pytest tests/test_smoke.py -q
  ls .claude/agents/*.md | wc -l
  systemctl is-active dqiii8-bot
If anything is misaligned: run /audit, generate a new checkpoint, delete the old one.
PERMISSION GRANTED: You may create, update, and delete files in docs/CHECKPOINT_*.md autonomously.

## Projects
Each project lives in my-projects/{name}/ and contains its own PROJECT.md.
To discover active projects and their context, scan:
  ls my-projects/*/PROJECT.md
Read the PROJECT.md of any project before working on it.
Never hardcode project lists here - PROJECT.md is the source of truth per project.

## Rules
- RULE file at project root - always read and follow
- Cheapest tier first (C>B>A>S), never pay when free works
- Never edit .env, CLAUDE.md, .credentials.json from code
- Auto-commit on session close via stop.py hook
- PermissionAnalyzer: APPROVE/DENY/ESCALATE every tool use

## Plugins (Claude Code)
Permanent: superpowers, episodic-memory, omc, frontend-design, firecrawl,
  hookify, semgrep, context7, code-review, skill-creator, figma,
  code-simplifier, pr-review-toolkit, claude-md-management
On-demand: Tier 3 auto-install via PROJECT.md "Plugins:" field
  Available: playwright, greptile, pyright-lsp, superpowers-lab
Config: config/claude_settings_template.json, bin/plugin_manager.py
