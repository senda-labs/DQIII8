# Plan Gate — Escalation to Opus (Tier S)

Referenced by `.claude/rules/03_tiering_and_routing.md` §Escalation to Opus and by
`rules_dispatcher.py` alias `plan-gate`. This is the canonical statement of the gate.

## When to escalate a PLAN to Opus

Escalate ONLY when `DQIII8_MODE=autonomous` AND the plan meets ≥1 criterion:
- Prompt < 15 words (vague intent — needs adversarial interpretation).
- Plan touches ≥5 files.
- Architectural decision with multiple valid paths (no single obvious answer).

## Hard limits
- Maximum **1** Opus escalation per task. Never re-escalate after Opus responds.
- Opus is for **plan review / adversarial critique only** — never initial generation
  (see § REGLA NIM in `00_core_behavior.md`: Anthropic-only vigente — Sonnet does the
  initial plan, Opus only ever attacks/reviews it).
- Opus receives: the plan + full project context + original spec. Its job is to attack
  the plan: missing edge cases, contract violations, hidden coupling, cheaper paths.

## Reality note
There is NO automatic code path that escalates a failed free-tier chain into
Anthropic — `"anthropic"` appears in no `FALLBACK_CHAIN` value in
`openrouter_wrapper.py`. Opus/Sonnet are reached only via static `AGENT_ROUTING`
entries (e.g. `orchestrator`, `code-reviewer`) or explicit user request. Treat this
gate as a decision rule for the orchestrating session, not an implemented wrapper
feature.
