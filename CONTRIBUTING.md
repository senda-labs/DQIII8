# Contributing to JARVIS

## Development Setup

```bash
git clone https://github.com/ikermartiinsv-eng/jarvis
cd jarvis
cp .env.example .env   # fill your API keys
pip install black ruff pytest
```

## Commit Conventions

Use [Conventional Commits](https://www.conventionalcommits.org/):

| Type | When to use |
|------|-------------|
| `feat` | New feature or agent |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `style` | Formatting (Black/Ruff) |
| `refactor` | Code restructure, no behavior change |
| `test` | Adding or updating tests |
| `chore` | Maintenance, dependency updates |
| `ci` | CI/CD pipeline changes |

Example: `feat: add youtube-analytics agent for MemoryLayer`

## Adding a New Agent

1. Create `.claude/agents/[name].md` following existing agent format
2. Add a trigger row to the delegation table in `CLAUDE.md`
3. Add triggers to `tests/test_agent_triggers.py`
4. Add a row to the agents table in `README.md`
5. Update `CHANGELOG.md` under `[Unreleased]`

## Adding a New Skill

1. Create `skills-registry/custom/[name]/SKILL.md`
2. Test the skill manually: `/[skill-name]`
3. Add to `skills-registry/INDEX.md` with status `reviewed`
4. Never load skills from `cache/` without INDEX.md approval

## Running Tests

```bash
python3 -m pytest tests/ -v
```

## Model Routing Rules

- Default to the **lowest tier** that can solve the task
- Tier 1 (Ollama): python, refactor, debug, git ops — `$0`
- Tier 2 (Groq/OpenRouter): review, research, analysis — `$0`
- Tier 3 (Claude API): architecture, finance, creative, /mobilize — paid
- Classify before escalating: `python3 bin/openrouter_wrapper.py classify "[prompt]"`

## Prohibited Actions

See `.claude/rules/jarvis-prohibitions.md` for the full list. Key rules:

- Never write to `.env`, secrets, or credential files
- Never modify `CLAUDE.md` or `database/schema.sql` without explicit user request
- Never delete data from `jarvis_metrics.db`
- Never force-push or rebase `master` without user confirmation
- Stop and re-plan if execution diverges — never push through broken state
