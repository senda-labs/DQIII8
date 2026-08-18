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
- Destructive / irreversible actions (rm -rf, DROP, force-push, schema change) → STOP, notify user, wait.
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
Cadena canónica multi-tier: `C → B → B+ → A → S` — **DORMANTE**, ver § REGLA NIM abajo.
Full table: `.claude/rules/03_tiering_and_routing.md`

## REGLA NIM — Anthropic-only vigente (non-negotiable)

**Directiva del usuario (2026-08-18): ninguna API de proveedor no-Anthropic funciona hoy
(NIM confirmado 403 desde 2026-08-16; Groq/Ollama/GitHub-free no operativos hasta nueva
verificación). Solo Sonnet/Opus. Cadena multi-tier dormante, no eliminada.**

**Agentes vigentes bajo Anthropic-only:** `context-probe`, `code-reviewer`, `code-validator`,
`finance-specialist`, `auditor`, `orchestrator`, `tax-auditor`, `closing-specialist` — todos
Sonnet, salvo revisión adversarial final (Opus, nunca generación inicial).

Reactivación multi-tier: requiere (1) probe manual humano con 200 real en
`POST /v1/chat/completions` (un 200 en `GET /v1/models` no cuenta) y (2) confirmación
explícita del usuario levantando también la directiva Anthropic-only — dos gates
independientes. Un agente NUNCA declara la reactivación por su cuenta.

Historial completo (catálogo de modelos NIM, fallback chain de 7 claves, namespace collision
`AGENT_ROUTING` vs `.claude/agents/*.md`, checklist de reactivación):
`.claude/rules_db/archive/multi-tier-dormant-2026-08.md`.

**Cómo llamar (Anthropic-only, hoy):**
Usar el Agent tool (Sonnet por defecto) o `claude -p` directo. El wrapper
`bin/core/openrouter_wrapper.py --agent <agente>` sigue existiendo para cuando se reactive
el multi-tier, pero hoy toda ruta que no sea Anthropic falla — no invocarlo salvo para probes
de reactivación explícitamente pedidos por el usuario.
