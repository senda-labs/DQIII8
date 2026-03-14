# Changelog

All notable changes to JARVIS are documented here.
Format: [keepachangelog.com](https://keepachangelog.com/es/1.0.0/)

## [Unreleased]

### Planned
- YouTube Analytics integration for MemoryLayer
- DuckDB migration for auditor analytics (>100k rows)
- VPS monitoring dashboard (agents, RAM, video queue)

## [0.5.0] — 2026-03-14

### Added
- CI/CD with GitHub Actions: black + ruff lint + CLAUDE.md line count validation
- Professional README with ASCII architecture diagram and routing table
- `.env.example` for clean onboarding
- `git push` after every auto-commit in `stop.py` hook (section 2b)
- Agent trigger coverage tests (`tests/test_agent_triggers.py`)
- `CONTRIBUTING.md` with agent and skill creation guides
- `pyproject.toml` for Black/Ruff/pytest configuration

### Changed
- `tasks/lessons.md`: standardized all entries to single-line format `[DATE] [KEYWORD] cause → fix`

## [0.4.0] — 2026-03

### Added
- Obsidian Brain (Phase 5.5): `/handover`, `/weekly-review` skills
- MemoryLayer SQLite for video history tracking
- Wave 2 agents: `content-automator`, `data-analyst`, `creative-writer`
- Gemini background code review (`bin/gemini_review.py`)
- instinct extraction from `lessons.md` → `instincts` table in SQLite

## [0.3.0] — 2026-03

### Added
- VPS setup: Ubuntu 24.04, tmux, SSH keys, `j.sh` entry point
- 3-tier model routing: Ollama → OpenRouter → Claude API
- Full hook system: `pre_tool_use.py`, `post_tool_use.py`, `stop.py`, `session_start.py`
- `/audit` skill with health scoring and report generation
- `/mobilize` multi-agent coordination protocol
- Auditor agent with 7-day auto-trigger

## [0.2.0] — 2026-03

### Added
- Wave 1 agents: `python-specialist`, `git-specialist`, `code-reviewer`, `orchestrator`
- SQLite metrics DB: `sessions`, `agent_actions`, `instincts`, `audit_reports` tables
- `bin/openrouter_wrapper.py` with `classify` command for automatic tier routing
- `bin/ollama_wrapper.py` for local Tier-1 model access

## [0.1.0] — 2026-03

### Added
- Initial JARVIS system constitution (`CLAUDE.md`)
- `j.sh` command with `--model`, `--status`, `--audit`, `--classify` flags
- 4 MCPs: filesystem, github, fetch, sqlite
- `tasks/lessons.md` self-improvement log
- `database/schema.sql` with full metrics schema
