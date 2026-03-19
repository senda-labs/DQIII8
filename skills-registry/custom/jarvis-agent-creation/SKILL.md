---
name: dqiii8-agent-creation
version: 1.0.0
source: git-analysis/dqiii8
analyzed_commits: 50
analyzed_date: 2026-03-12
repos: [$JARVIS_ROOT]
---

# DQIII8 Agent Creation

## Detected pattern

DQIII8 agents are created in waves (batches) with identical structure.
Each agent defines: trigger, role, protocol (numbered), feedback format, and rules.

**Evidence from history:**
- `feat: Agents Wave 2 — data-analyst, creative-writer, research-analyst` (2aadb19) — 3 simultaneous files
- `feat: unified routing 3 tiers — Ollama+Groq+OpenRouter+Sonnet` (ba60bc7) — includes code-reviewer, content-automator, git-specialist
- `feat: content-automator agent` (dd01d41) — individual agent with iteration
- `feat: Phase 1 complete - agents Wave 1` — first batch

**Detected co-changes:**
- `.claude/agents/*.md` always goes with routing update in `CLAUDE.md` and/or `bin/openrouter_wrapper.py`

## When to use this skill

- Create a new specialized agent
- Add an agent for a new domain (e.g. DevOps, mobile, finance)
- Check if an existing agent covers the trigger before creating a new one
- Define the correct tier model for the agent

## Canonical agent structure for DQIII8

File: `.claude/agents/{agent-name}.md`

```markdown
---
name: {agent-name}
model: {tier}:{model}
isolation: worktree  # only if writing code that could break the repo
---

# {Readable Name}

## Trigger
{keyword1} | {keyword2} | "example phrase" | {condition}.

## Role
{One sentence: what it does, what it does NOT do}.

## Protocol
1. {First concrete and verifiable step}.
2. {Second step}.
3. {Explicit verification}.
4. Write result to `tasks/results/{agent}-[timestamp].md`.

## Feedback format
\```
[NAME] ✅/❌ {1-line summary}
{key metric}: {value}
\```

## Rules
- {Domain-specific rule}.
- Escalate to orchestrator if {complexity condition}.
```

## Existing agents (do not duplicate)

| Agent | Model | Key triggers |
|-------|-------|-------------|
| python-specialist | ollama:qwen2.5-coder:7b | .py, traceback, refactor, debug |
| git-specialist | ollama:qwen2.5-coder:7b | commit, branch, PR, merge, push |
| code-reviewer | groq:llama-3.3-70b-versatile | review, "is this ok", worktree |
| orchestrator | claude-sonnet-4-6 | /mobilize, coordinate, 3+ domains |
| content-automator | openrouter/nvidia/nemotron | video, TTS, subtitles, reels |
| data-analyst | claude-sonnet-4-6 | WACC, DCF, chart, Excel |
| creative-writer | openrouter/meta-llama/llama-3.3-70b | chapter, scene, novel, story, fiction |
| auditor | claude-sonnet-4-6 | /audit, "what's failing", metrics |
| research-analyst | openrouter/stepfun/step-3.5-flash | research, investigate, document |

## Workflow: create a new agent

### 1. Verify no existing coverage

```bash
grep -r "trigger\|Trigger" $JARVIS_ROOT/.claude/agents/ | grep -i "{your-keyword}"
```

### 2. Choose model by CLAUDE.md tier routing

- Simple/local task → `ollama:qwen2.5-coder:7b`
- Review/analysis → `groq:llama-3.3-70b-versatile`
- Media/content → `openrouter/nvidia/nemotron-nano-12b-v2-vl:free`
- Architecture/finance/creative → `claude-sonnet-4-6`

### 3. Create the `.claude/agents/{name}.md` file

Use the canonical structure. Critical points:
- **Trigger**: exact phrases the user says, not abstract concepts
- **Protocol**: always numbered, last step = write to `tasks/results/`
- **Feedback format**: always include `[NAME]` prefix in uppercase

### 4. Register in `bin/openrouter_wrapper.py` if using OpenRouter/Groq

```python
AGENT_ROUTING = {
    "{agent-name}": ("{provider}", "{model-id}"),
}
```

### 5. Update Delegation table in `CLAUDE.md`

```markdown
| {trigger keywords} | {agent-name} | {isolation or —} |
```

### 6. Commit

```bash
# For a batch of agents:
git commit -m "feat: Agents Wave N — {agent1}, {agent2}, {agent3}"

# For individual agent with iteration:
git commit -m "feat: agent {agent-name}"
```

## Files involved

| File | When to touch it |
|------|-----------------|
| `.claude/agents/{name}.md` | Always (main file) |
| `CLAUDE.md` § Delegation | Always (routing table) |
| `bin/openrouter_wrapper.py` | If using OpenRouter/Groq (AGENT_ROUTING) |
| `bin/j.sh` | Only if needs special flag in CLI |

## Detected anti-patterns (from fix: commits)

- **Trigger too generic** → collisions between agents; be specific with exact phrases
- **Not updating CLAUDE.md Delegation** → the agent exists but is never auto-invoked
- **Forgetting the `Write result to tasks/results/` step** → orchestrator can't read the output
- **Using `isolation: worktree` unnecessarily** → slows things down; only if writing code that could break the repo
- **Wrong model** → do not use claude-sonnet-4-6 for tier-1 tasks; respect tier routing
