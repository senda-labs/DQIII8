# Core Behavior — DQIII8

## Zero-Complacency Protocol (non-negotiable)
- Validate the **real final artifact** (deployed service, API response, DOCX, DB row) — not just tests or logs.
- Attack the root cause. Never patch symptoms. Never silence errors without understanding them.
- If an error repeats: instrument a structural QA check that blocks delivery until resolved.
- Never declare success until the artifact is verified end-to-end.

## Autonomous Execution Rules
- Plans ≤5 steps, no destructive actions → execute autonomously, notify after.
- Plan touches ≥3 modules OR has ambiguous scope → enter plan mode first, wait for confirmation.
- Destructive / irreversible actions (rm -rf, DROP, force-push, schema change) → STOP, notify user, wait.
- Bug in production → fix immediately: read logs, isolate cause, resolve, verify. No hand-holding.

## Scope Discipline
- NEVER modify >3 files without a plan. Creep kills correctness.
- NEVER add features, abstractions, or error handling beyond what the task requires.
- NEVER write comments explaining WHAT code does — only WHY when non-obvious.

## Cost-First Rule (absolute)
Always start at the cheapest tier that can handle the task (C → B → B+ → A → S).
NEVER use Tier A/S for tasks Tier B can handle. Full table: `.claude/rules/03_tiering_and_routing.md`
