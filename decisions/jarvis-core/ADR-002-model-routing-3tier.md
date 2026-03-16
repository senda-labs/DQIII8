# ADR-002 — 3-Tier Model Routing

**Date:** 2026-03-12
**Status:** Accepted
**Project:** jarvis-core
**Deciders:** Iker, JARVIS

---

## Context

JARVIS agents were originally assigned models ad hoc — some used Sonnet for tasks
that Haiku or a free Groq model could handle, inflating API costs with no quality
benefit. There was no routing logic: every task went to the most capable (and
expensive) model available.

Additionally, the system had no classification mechanism — it was impossible to
automatically determine which tier a given prompt required.

## Decision

Adopt a **3-tier model routing system**:

| Tier | Provider | Model | When to use |
|------|----------|-------|-------------|
| 1 — local | Ollama | `qwen2.5-coder:7b` | Python, refactor, debug, git ops |
| 2 — cloud free | Groq | `llama-3.3-70b-versatile` | Code review, analysis, research |
| 2 — cloud free | OpenRouter | `nvidia/nemotron-nano-12b-v2-vl:free` | Video, TTS, subtitles, media |
| 2 — cloud free | OpenRouter | `qwen/qwen3-235b-a22b:free` | Research, documentation |
| 2 — cloud free | Claude API | `claude-haiku-4-5-20251001` | Creative writing, fast extraction |
| 3 — paid | Claude API | `claude-sonnet-4-6` | Finance, arch, mobilize, orchestration |

**Routing rule:** Use the lowest tier that can resolve the task. Escalate only
when the lower tier fails. Never start at Tier 3 for tasks Tier 1 can handle.

**Orchestration agents** (`orchestrator`, `auditor`, `code-reviewer`) always run on
Tier 3 (`claude-sonnet-4-6`) because they make architectural decisions and spawn
subagents.

**Classification:** `python3 bin/openrouter_wrapper.py classify "<prompt>"` → returns
`tier=N provider=X model=Y` at zero cost.

**Planner constant:** `CLAUDE_PLANNER_MODEL = "claude-sonnet-4-6"` must be used in
all multi-scene pipeline orchestration (scene_director.py, orchestrator.py).

## Consequences

**Positive:**
- ~70% reduction in Claude API spend (Tier-1 handles most coding tasks locally)
- Tier-2 free models cover research, review, and media pipeline
- Consistent cost tracking: `model_tier` column in `agent_actions` table
- Classification at $0 prevents accidental Tier-3 usage

**Negative / Trade-offs:**
- Tier-1 (Ollama) requires local GPU/CPU — cold starts add ~2s latency
- Free Tier-2 models have rate limits and occasional degraded quality
- Routing logic adds complexity — misclassification sends task to wrong tier

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| Always use Claude Sonnet | ~5x higher cost with no quality improvement for simple tasks |
| Two tiers (local + paid) | Missing free cloud tier leaves gap — many research tasks don't need paid |
| Per-task manual routing | Error-prone, doesn't scale, no enforcement mechanism |

---

## Invariants

```yaml
invariants:
  - id: "ADR-002-I2"
    description: "python-specialist agent must use Tier-1 Ollama model"
    paths:
      - ".claude/agents/python-specialist.md"
    must_contain:
      - "ollama:qwen2.5-coder:7b"
    message: "ADR-002 violation: python-specialist must use ollama:qwen2.5-coder:7b (Tier 1). Do not assign a paid model to routine Python tasks."

  - id: "ADR-002-I3"
    description: "orchestrator agent must use claude-sonnet-4-6"
    paths:
      - ".claude/agents/orchestrator.md"
    must_contain:
      - "claude-sonnet-4-6"
    message: "ADR-002 violation: orchestrator must use claude-sonnet-4-6 (Tier 3). Orchestration requires full reasoning capability."

  - id: "ADR-002-I4"
    description: "no deprecated model names in any agent file"
    paths:
      - ".claude/agents/python-specialist.md"
      - ".claude/agents/git-specialist.md"
      - ".claude/agents/code-reviewer.md"
      - ".claude/agents/orchestrator.md"
      - ".claude/agents/auditor.md"
    must_not_contain:
      - "claude-3-haiku"
      - "claude-3-sonnet"
      - "claude-3-opus"
      - "gpt-4"
      - "gpt-3.5"
    message: "ADR-002 violation: deprecated model name found in agent file. Use only approved tier models listed in ADR-002."
```
