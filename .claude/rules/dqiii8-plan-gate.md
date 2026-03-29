# DQIII8 — Plan Quality Gate (Opus Escalation)

> Applies when `DQIII8_MODE=autonomous` and session model is Sonnet.

## When to escalate

After creating an implementation plan, self-assess against these criteria:

| Signal | Threshold |
|--------|-----------|
| User prompt is vague (< 15 words, no specifics) | Escalate |
| Plan touches ≥ 5 files or ≥ 3 modules | Escalate |
| Architectural decision with multiple valid paths | Escalate |
| Domain you lack context on (finance, video, ML) | Escalate |
| Plan steps are generic ("implement feature", "add tests") | Escalate |
| Clear, scoped task with obvious implementation | Do NOT escalate |

## How to escalate

Spawn an Opus subagent with `model: "opus"` via the Agent tool:

```
Agent(
  subagent_type: "Plan",
  model: "opus",
  prompt: """
  Review this implementation plan for task: {task_description}

  PLAN:
  {your_plan}

  CONTEXT:
  - Project: DQIII8 (autonomous AI orchestration on VPS)
  - Key files involved: {list}
  - User's original prompt: {prompt}

  Evaluate:
  1. Does the plan address the actual goal, not just the literal words?
  2. Are there critical steps missing?
  3. Is the sequence optimal?
  4. Are there risks the plan ignores?

  Respond with:
  - VERDICT: APPROVE | ADJUST
  - If ADJUST: provide the revised plan with specific changes marked.
  - Keep response under 300 words.
  """
)
```

## After Opus responds

- **APPROVE**: Proceed with original plan.
- **ADJUST**: Replace your plan with Opus's revised version. Do NOT re-escalate.

## Cost guard

- Maximum 1 Opus escalation per task. If Opus already reviewed, proceed.
- Never escalate for: single-file edits, documentation, git operations, simple bug fixes.
