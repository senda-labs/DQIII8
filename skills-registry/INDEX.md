# Skills Registry — DQIII8

## Custom Skills (`.claude/skills/`)

| Skill | Category | Status | Description |
|-------|----------|--------|-------------|
| audit | Ops | Active | Full system health audit — DB, pipeline, agents, error log, scored report |
| blue-team | Security | Active | Defensive security — patches red-team findings, hardens code and permissions |
| checkpoint | Git | Active | Save session state via git commit before risky or significant changes |
| gemini-review | Quality | Active | Efficiency audit on Python files via Aider + Gemini 2.0 Flash |
| handover | Ops | Active | End-of-session handover note — saves to sessions/, commits and pushes |
| instinct-status | Diagnostic | Internal | Shows learned instincts from dqiii8.db grouped by project and confidence |
| intl-reports | Pipeline | Active | Generates internationalisation reports (Diagnóstico + Plan) for Spanish SMEs |
| mobilize | Agents | Active | Multi-agent coordination for tasks spanning 3+ distinct domains |
| mode | Ops | Active | Activates a work mode: analyst / coder / creative — persists for session |
| prompt-optimize | Prompting | Active | Analyzes and optimises prompts across DQIII8 routing dimensions |
| quality-gate | Quality | Active | Format → lint → type-check → test → security scan pipeline |
| red-team | Security | Active | Adversarial OWASP/prompt-injection testing — user-invoked only |
| security-cycle | Security | Active | Iterative red-team/blue-team cycles until 0 CRITICAL/HIGH findings |
| skill-create | Learning | Active | Extracts git patterns and generates SKILL.md files in skills-registry/custom/ |
| test-team | Agents | Internal | Agent coordination test (research-analyst → python-specialist handoff) |
| transcript-learn | Learning | Active | Converts video transcripts to DQ knowledge chunks, skills, or agent defs |
| weekly-review | Ops | Active | Weekly dashboard update — reads sessions, queries metrics, regenerates 00_DASHBOARD.md |

## Rules

- Skills with status `Internal` are diagnostic/test tools — not for direct user invocation.
- Skills with status `Experimental` are queued for review before production use.
- External cache skills (downloaded via `/skills-sync`) live in `skills-registry/cache/` (gitignored).

## Adding skills

See `skills-registry/README.md` for structure and loading rules.
Place custom skills in `.claude/skills/{name}/SKILL.md` and update this index.
