# ADR-001: Context Efficiency Architecture
**Date:** 2026-03-30
**Status:** ACCEPTED
**Author:** Principal Architect (Claude Sonnet 4.6)

---

## Problem Statement

Every `.md` file in `.claude/rules/` is injected by Claude Code as a `<system-reminder>` block **on every conversation turn** (not just at session start). With 32 files totalling ~34 KB (~6,400 tokens), each turn consumes 6,400 tokens of re-injected static text. Over a 50-turn session this amounts to **~320,000 tokens** burned on rules alone — before counting tool outputs, responses, or conversation history. Compaction triggers at ~500K tokens, so rules alone account for **64% of the compaction budget**.

### Measured baseline (2026-03-30)
| Source | Files | Lines | Tokens/turn |
|--------|-------|-------|-------------|
| `.claude/rules/` | 32 | 1,032 | ~6,400 |
| CLAUDE.md | 1 | 69 | ~550 |
| session_start hook | — | — | ~211 |
| context-mode SessionStart | — | — | ~365 |
| **Baseline per turn** | | | **~7,526** |

---

## Options Evaluated

### A — Anthropic Prompt Caching
**Mechanism:** Mark system prompt as cacheable via `cache_control` headers in API calls.
**Verdict: NOT APPLICABLE.**
Claude Code CLI manages API calls internally and does not expose caching headers to hooks. While Anthropic does cache system prompts automatically, the `<system-reminder>` injections appear as *conversation-turn text*, not as system-prompt text — they are NOT eligible for prompt caching. Zero control surface from our side.

### B — Haiku Router: summarise tool outputs before returning them to context
**Mechanism:** Intercept every Bash/Read tool output via PostToolUse, route to Haiku 4.5 (~$0.25/1M tokens), return a compressed summary.
**Verdict: OVERKILL, wrong problem.**
- Adds 300-500ms latency per tool call (Haiku round-trip).
- Adds API cost per tool call (previously zero).
- Does NOT solve the *rules re-injection* problem — that happens regardless of tool output size.
- context-mode's `pretooluse.mjs` routing block already handles the large-output case by redirecting to `ctx_batch_execute`. Duplicating this logic in a Haiku layer is redundant.
- Only effective for sessions dominated by gigantic read/git-log outputs, which is a secondary problem here.
- **Conclusion: useful as last resort, not the right primary lever.**

### C — Dynamic Memory / RAG on rules
**Mechanism:** Replace static rules files with a vector-indexed knowledge base; inject only relevant rules per prompt via embedding similarity search.
**Verdict: ENGINEERING OVERKILL for the actual gap.**
- System already has `vault_memory` (SQLite) + episodic-memory MCP. Adding a third memory layer for rules adds maintenance burden.
- Rules files are short, deterministic, and always relevant in aggregate. The "relevant subset" is unpredictable — any rule can apply at any time.
- Setup time > 4 hours; benefit uncertain.
- **Conclusion: valid long-term direction, not the right lever for this sprint.**

---

## Decision: **Rules Consolidation + Conditional Loading Gate**

The most effective intervention requires no new infrastructure:

### Primary — Rules Consolidation (zero-risk, immediate)
Reduce `.claude/rules/` from **32 files → 17 files** by merging related files, eliminating redundancy, and moving rarely-triggered guides to on-demand skills.

**Target reduction: ~6,400 → ~3,200 tokens/turn (-50%)**

### Secondary — Conditional Loading Gate (new hook logic)
Add a lightweight gate in `pre_tool_use.py` that detects "likely large output" commands (git log > N, ls -la on `/`, cat > 200 lines) and emits an `additionalContext` warning urging truncation — complementing what `context-mode pretooluse.mjs` already does.

This gate does NOT add API cost, does NOT add latency for approved calls, and can be implemented in < 30 lines.

---

## Implementation Plan

### Step 1 — Rules Consolidation (Fase 2)

| New File | Merges | Lines Before | Lines After | Saved |
|----------|--------|-------------|-------------|-------|
| `git-safety.md` | bash-safety + dqiii8-git-gitignore | 78 | 50 | 28 |
| `routing.md` | ml-routing + token-routing | 113 | 70 | 43 |
| `python.md` | dqiii8-python + python/coding-style + python/patterns + python/hooks | 109 | 60 | 49 |
| `common/quality.md` | common/coding-style + common/security | 77 | 50 | 27 |
| `common/workflow.md` | common/development-workflow + common/hooks + common/patterns | 98 | 60 | 38 |
| `dqiii8-ops.md` | dqiii8-autonomy + dqiii8-prohibitions + claude-md-limit | 30 | 22 | 8 |
| `dqiii8-tools.md` | dqiii8-cli-tools + dqiii8-knowledge + dqiii8-github-research + dqiii8-telegram | 60 | 40 | 20 |
| **DELETE** | dqiii8-gemini-review (→ skill only) | 17 | 0 | 17 |
| **DELETE** | python/security + python/testing (covered by common/quality) | 68 | 0 | 68 |
| **KEEP** | dqiii8-error-prevention, dqiii8-context-window, dqiii8-deliverables, dqiii8-plan-gate, workspace, common/agents, common/git-workflow, common/performance, common/testing | — | — | — |

**Result: 32 files → 17 files | 1,032 lines → ~580 lines | ~6,400 → ~3,600 tokens/turn**

### Step 2 — Output Guard (Fase 2)
Add `_large_output_guard()` to `pre_tool_use.py`: detects Bash commands matching
`git log`, `find /`, `ls -la [root paths]`, `cat` without `head` piping.
Emits deny with suggestion to pipe through `head -N` or use `ctx_batch_execute`.

### Step 3 — Skills Audit (Fase 3)
Audit 19 skills against new consolidated rules. Identify redundant skills.

---

## Expected Savings

| Scenario | Tokens/turn before | Tokens/turn after | Δ |
|----------|-------------------|-------------------|---|
| Static rules | 6,400 | 3,200 | -3,200 |
| Session baseline | 7,526 | 4,326 | -3,200 |
| **50-turn session** | 376,300 | 216,300 | **-160,000 (-42%)** |
| **Compaction trigger (500K)** | ~66 turns | ~115 turns | **+75% longer sessions** |

Sessions will last ~75% longer before compaction. Mission continuity improves dramatically.

---

## Risk Assessment
| Change | Risk | Mitigation |
|--------|------|------------|
| Merge rules files | LOW — content preserved, only structure changes | Git history preserves originals; can revert in 1 commit |
| Delete python/security + python/testing | LOW — content absorbed into common/quality | Content fully merged before deletion |
| Delete dqiii8-gemini-review | ZERO — skill already exists | |
| Output guard in pre_tool_use | LOW — exits 0 on all errors | try/except around entire guard |
