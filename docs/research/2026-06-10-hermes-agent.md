# Research C3 — Hermes Agent (NousResearch lineage)

**Date:** 2026-06-10
**Task:** Bloque C / Task C3 of `docs/superpowers/plans/2026-06-10-dqiii8-execution-plan-compiler.md`
**Question:** Do Hermes' tooling/planning patterns offer anything worth importing into DQIII8's
router (`AGENT_ROUTING`, `bin/core/openrouter_wrapper.py:93`) or the new zero-LLM
`plan_compiler` (Bloque B)?
**Method:** `gh` CLI unavailable on this VPS and the GitHub MCP returned `Bad credentials`;
located repos via WebSearch (NousResearch lineage), then `git clone --depth 1` to `/tmp/oss-research/`
for static reading. No code from the clones was executed.

## Sources

- [NousResearch/Hermes-Function-Calling](https://github.com/NousResearch/Hermes-Function-Calling) — the focused tool-calling reference framework (~9 Python files). Read: `functioncall.py`, `functions.py`.
- [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) — "the agent that grows with you", a large monolithic personal-assistant (`cli.py` 625 KB, `hermes_state.py` 197 KB, `agent/` ~80 modules). Read: `AGENTS.md` (the design-intent doc), `agent/` module index.
- [hermes-agent docs](https://hermes-agent.nousresearch.com/docs/) · mirror [mudrii/hermes-agent-docs](https://github.com/mudrii/hermes-agent-docs).

Both repos are real and credible → this is a **positive** result (PASS), not a negative-result close.

---

## What Hermes actually does

### A. Hermes-Function-Calling — the planning loop & tool registry

**Tool registry** (`functions.py`): plain Python functions decorated with LangChain's `@tool`.
The whole "registry" is the module itself — `functions.get_openai_tools()` walks the module to emit
OpenAI-format JSON schemas; dispatch is `getattr(functions, tool_call["name"])(*args.values())`
(`functioncall.py:74-82`). Adding a tool = writing one function. No DB, no manifest, no daemon.

**Planning loop** (`functioncall.py:102-161`): a **recursive ReAct** loop, not plan-then-execute and
not a tree. Each turn: run inference → parse `<tool_call>` → execute → append a `<tool_response>`
message → recurse. Bounded by `max_depth=5`. One model, one growing message list. Planning is
*implicit* in the model's chain-of-thought; there is no separate plan artifact.

**Context management**: naive full-history accumulation (`prompt.append(...)` every turn),
`max_new_tokens=1500`. No compaction, no summarization in this repo.

**Error recovery** (`functioncall.py:121-153`): the notable part. On a schema-validation failure or a
runtime exception, instead of aborting it injects the traceback back into the conversation as a
`<tool_response>` ending in *"Please call this function again with correct arguments"*, then recurses.
Self-correction by re-prompting, hard-capped by `max_depth`. Same shape DQIII8 already has in
`ril.py` (retry ≤2 → `degraded_success`).

> Note: `functions.code_interpreter` runs model-authored Python via bare `exec()` in-process — exactly
> the arbitrary-code-execution surface DQIII8's permission hooks exist to prevent. Mentioned only as a
> contrast; not a candidate.

### B. hermes-agent — the design philosophy (the valuable part)

The 70 KB `AGENTS.md` is the asset here, not the code (the code is a sprawling multi-provider
assistant: `agent/context_compressor.py`, `conversation_compression.py`, `context_engine.py`,
`error_classifier.py`, `curator.py`, `delegate_task`, toolsets, cron, kanban — far past DQIII8's needs).
Two sections converge almost exactly on DQIII8's own stated principles:

- **The Footprint Ladder** (`AGENTS.md:171-200`): a 6-rung "choose the least permanent surface that
  solves it" ladder for any new capability — *extend existing code → CLI command + skill →
  service-gated tool → plugin → MCP server → new core tool (last resort)*. Rationale: "every tool ships
  on every API call." This is wu wei stated as an engineering rubric, and it is structurally the same
  shape as DQIII8's cost-first tier ladder (C → B → B+ → A → S: start cheapest, escalate only on
  explicit match/failure).
- **"What we don't want"** (`AGENTS.md:96-126`): rejects speculative infra/hooks with no consumer,
  new env vars for non-secret config (`.env` = secrets only; behaviour goes in `config.yaml`), and a new
  core tool "when terminal + file already do the job." These are near-verbatim siblings of DQIII8's
  inviolable rules (never write `.env`, no new daemon the project doesn't measurably need).

---

## Comparison against DQIII8

| Axis | DQIII8 today | Hermes | Gap? |
|---|---|---|---|
| **Routing** | `AGENT_ROUTING` = static `name → (provider, model)` dict; `director.py` adds keyword/instinct classification. No agentic loop. | ReAct loop, model decides each tool call at runtime. | Different problem. Hermes routes *within* one model's turn; DQIII8 routes *across* tiers/agents. Not substitutable. |
| **plan_compiler (Bloque B)** | Deterministic, **zero-LLM**, ~0 ms, template → phases/audit/invariants. | Loop is LLM-driven at *every* step; "plan" is emergent, never materialised. | Philosophically opposite. Hermes is the anti-pattern plan_compiler is designed to avoid (no determinism, no upfront audit/exit-criteria). |
| **Tool registry** | Agents are config rows + Python modules; no per-call tool schema tax. | `@tool` functions auto-emitted to JSON schema each call. | DQIII8 doesn't expose a flat tool list to one model, so the mechanism doesn't map. |
| **Error recovery** | `ril.py`: retry ≤2 → `degraded_success`; `phase_guard.py` invariants. | Inject-traceback-and-re-prompt, capped by `max_depth`. | DQIII8 already has the stronger, deterministic version. |
| **Context mgmt** | Rules-dispatcher RAG (200–800 tokens/turn), no full-history bloat. | Naive accumulation (FC repo); heavy compressor modules (agent repo). | DQIII8's approach is leaner and already chosen on purpose (ADR-001). |

---

## Verdicts

### 1. ReAct recursive tool-calling loop (`functioncall.py`) — **DISCARD**
It is LLM-driven at every step, the exact opposite of `plan_compiler`'s zero-LLM determinism, and it
solves intra-turn tool selection — a problem DQIII8's cross-tier router does not have. Adopting it would
add per-call LLM cost and non-determinism for no measurable gain. Wu wei: do nothing.

### 2. `@tool`-module tool registry + auto JSON-schema (`functions.py`) — **DISCARD**
Elegant for a single-model OpenAI-tools agent, but DQIII8 doesn't present a flat tool list to one model;
its unit of dispatch is the *agent*, already covered by `AGENT_ROUTING` + `config/domain_agent_map.json`.
No gap to fill. (And the bundled `code_interpreter` `exec()` is precisely what DQIII8's hooks forbid.)

### 3. Inject-traceback-and-retry error recovery — **DISCARD (already present, stronger)**
DQIII8's `ril.py` (retry ≤2 → `degraded_success`) plus `phase_guard.py` invariants are the deterministic
superset of Hermes' re-prompt-until-`max_depth`. Nothing to import; the existing port from Orchestrator v4
is better suited to the zero-LLM, batch context.

### 4. The Footprint Ladder + "What we don't want" rubric (`AGENTS.md`) — **INTEGRATE (as documentation only)**
This is the one genuinely useful artifact. It is an independent, externally-validated restatement of
DQIII8's own cost-first + wu-wei doctrine, expressed as a concrete decision ladder. **Integrate as prose,
not code**: a short "Capability Footprint Ladder" note appended to the routing rules
(`.claude/rules/03_tiering_and_routing.md`) or cited in the plan_compiler design, mapping its 6 rungs onto
DQIII8's `C → B → B+ → A → S` ladder and the "no new daemon/DB/env-var unless measurably needed" filter.
Zero new surface — which is itself the point the ladder makes. *This is the only INTEGRATE, and it adds no
runtime code.*

---

## Conclusion

Hermes' *implementation* (ReAct loop, `@tool` registry, re-prompt recovery) is built for a different
problem — one model choosing tools mid-turn — and is philosophically opposed to the deterministic, zero-LLM
`plan_compiler`. All three implementation patterns: **DISCARD**. The lasting value is the hermes-agent
`AGENTS.md` **Footprint Ladder**, which independently validates DQIII8's cost-first/wu-wei stance and is
worth citing as doctrine — a documentation-only **INTEGRATE** with no new code. Net change to the codebase
from this research: none required; one optional doc cross-reference.

TASK C3 RESULT: PASS — Located & cloned both credible Hermes repos (gh/MCP unavailable → WebSearch + git clone to /tmp). Extracted tool registry (@tool module + getattr dispatch), planning loop (recursive ReAct, max_depth=5), context mgmt (naive accumulation), error recovery (inject-traceback-and-retry). Verdicts: ReAct loop DISCARD, tool registry DISCARD, error recovery DISCARD (ril.py already stronger), AGENTS.md Footprint Ladder INTEGRATE as documentation-only doctrine cross-ref. Wu wei honored: zero new runtime code. Doc written to docs/research/2026-06-10-hermes-agent.md.
