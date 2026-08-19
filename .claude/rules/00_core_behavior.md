# Core Behavior — DQIII8

## Zero-Complacency Protocol (non-negotiable)
- Validate the **real final artifact** (deployed service, API response, DOCX, DB row) — not just tests or logs.
- Attack the root cause. Never patch symptoms. Never silence errors without understanding them.
- If an error repeats: instrument a structural QA check that blocks delivery until resolved.
- Never declare success until the artifact is verified end-to-end.

## Clarify Before Acting (non-negotiable)
- Prompt vague/short and doesn't fully pin down intent + scope + expected output quality → ASK first, don't guess-and-iterate.
- Skip only if the prompt already answers: (1) exact goal, (2) in/out scope, (3) enterprise-grade "done" bar.
- One sharp clarifying round beats multiple correction cycles.

## Autonomous Execution Rules
- Plans ≤5 steps, no destructive actions → execute autonomously, notify after.
- Plan touches ≥3 modules OR has ambiguous scope → enter plan mode first, wait for
  confirmation, then run `/panel-review <plan-file>` before implementation.
- Destructive / irreversible actions (DROP, live-schema change, `rm -rf` de datos) → STOP, notify user, wait.
  Excepciones ya cerradas en código (SSOT `02_hooks_and_permissions.md`): `rm -rf` de build/cache
  = auto-aprobado (§ALLOWED_DELETIONS); `git push --force` = DENY, la confirmación no lo desbloquea.
- Bug in production → fix immediately: read logs, isolate cause, resolve, verify. No hand-holding.

## Scope Discipline
- NEVER modify >3 files without a plan. Creep kills correctness.
- NEVER add features, abstractions, or error handling beyond what the task requires.
- NEVER write comments explaining WHAT code does — only WHY when non-obvious.

### Priority Ladder (Karpathy/Anthropic minimalism — every line is a liability)
Before writing code, stop at the first rung that resolves it: skip (YAGNI) → reuse
(grep first) → stdlib → installed dependency → one line → minimum new code. Doesn't
override validation/security/data-loss guards. `/panel-review` flags skipped rungs.

## Cost-First Rule (absolute)
Always start at the cheapest tier that can handle the task.
Full table: `.claude/rules/03_tiering_and_routing.md`

## REGLA NIM — Anthropic-only vigente (non-negotiable)
- Directiva usuario 2026-08-18: ningún proveedor no-Anthropic funciona (NIM 403 desde
  2026-08-16; Groq/Ollama/GitHub-free sin verificar). Solo Sonnet (default) / Opus
  (revisión adversarial final, nunca generación inicial). Multi-tier dormante, no eliminado.
- Delegar con el Agent tool o `claude -p`. NO invocar `bin/core/openrouter_wrapper.py`
  salvo probes de reactivación pedidos explícitamente por el usuario.
- Reactivación = dos gates independientes: (1) probe humano con 200 real en
  `POST /v1/chat/completions` (un 200 en `GET /v1/models` no cuenta) y (2) confirmación
  explícita del usuario levantando la directiva. Un agente NUNCA la declara por su cuenta.
- Roster/bindings vigentes (SSOT `AGENT_ROUTING`) → `.claude/rules/03_tiering_and_routing.md`.
  Historial completo → `.claude/rules_db/archive/multi-tier-dormant-2026-08.md`.
