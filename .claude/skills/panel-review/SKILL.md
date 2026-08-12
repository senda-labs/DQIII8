---
name: panel-review
description: Adversarial review of a plan file — 3 heterogeneous NIM seats (breadth) + exactly one Opus pass (depth) — before implementation of a ≥3-module or ambiguous-scope change.
command: /panel-review
allowed-tools: [Bash, Read]
user-invocable: true
---

# /panel-review — Plan Adversarial Review Panel

Run before implementing any plan that touches ≥3 modules or has ambiguous scope,
after plan-mode design and before writing code.

## Usage

```
/panel-review <plan-file>
```

Runs `python3 bin/tools/panel_review.py <plan-file>`.

## What it does

1. **3 heterogeneous NIM seats** (genuinely distinct models, not aliases of the
   same one — verified against `AGENT_ROUTING`):
   - `python-specialist` (DeepSeek V4 Flash) — API/contract correctness, test coverage
   - `data-specialist` (Mistral 675B) — data integrity, blast radius, rollback/undo path
   - `safety-checker` (NemoGuard 8B) — destructive-operation and permission review
   These are $0, fast, breadth-first pre-filters. They read the plan and the repo
   and must cite `file:line` for every finding — uncited findings are discarded
   by the orchestrator, not just flagged.
2. **Exactly ONE Opus adversarial pass** (`code-reviewer` agent → `claude-opus-4-8`).
   **This spends the operator's own Claude Code session quota** — no
   `ANTHROPIC_API_KEY` is configured, so it runs as a nested `claude -p` OAuth call,
   not a free NIM request. It reuses the *existing* single-Opus-escalation
   allowance defined in `.claude/rules_db/dqiii8-plan-gate.md` (max 1 per task) —
   it is not an additional or second Opus budget. No iteration, no forced
   dissent, no re-voting loop: one pass, one verdict.
3. **Report**: written to `database/audit_reports/panel-review-YYYY-MM-DD-HH-<slug>.md`
   (tracked path, mirrors the `audit` skill). Never `docs/superpowers/` — that
   path is gitignored, which is exactly how a prior review's findings ledger
   was permanently lost (see session 2026-08-11 handover).
4. **Verdict is advisory, not a gate.** The tool reports; the calling session
   (CC) is responsible for addressing each cited finding before implementation
   proceeds.

## Analysis procedure (v3, strict/structured)

Every seat is instructed to work through a fixed STRIDE-derived taxonomy —
Security / Correctness / DataIntegrity / Resilience / Operational — and for
each category either report a finding in a strict block format
(`[CATEGORY] [SEVERITY:P0-P3]` + `file:line` + one-line defect + concrete
exploit/failure scenario) or state explicitly "considered, no issues found."
Category/severity are advisory metadata (attached if present, never required
to survive); the **only hard discard gate is the file:line citation actually
existing in this repo** — anything discarded is still shown in a collapsed
"dropped findings" appendix with its reason (`no_citation`/`fake_path`),
never silently deleted, because silent deletion is indistinguishable from a
seat having genuinely found nothing.

Two extra safeguards, both added after live use surfaced real gaps:
- **Seat-degradation banner**: NIM has an internal fallback that can silently
  substitute a different provider/model per call. Confirmed live 2026-08-12:
  all 3 "heterogeneous" seats were actually served by the same
  `groq/llama-3.3-70b-versatile` model, collapsing 3 independent opinions into
  one model answering three times. The report now compares intended vs actual
  provider/model per seat and renders a loud banner when they diverge — never
  assume seat diversity without checking.
- **Opus-only "all clean" flag**: cheap seats returning zero verified findings
  is the observed baseline, not a signal (confirmed live: 3/3 NIM seats found
  nothing against a plan with a planted SQL injection + IDOR that Opus caught
  immediately). The report only calls out "unanimous clean bill" when the
  **Opus** seat specifically finds nothing — that's rare and actually means
  something.

There is deliberately no "find at least one issue per category" quota — on a
seat that has already fabricated a citation once (observed live: invented
`src/db.py:15` in a repo with no `src/` directory), a quota is a fabrication
incentive, not a rigor increase.

## Why this design (history)

An earlier draft used 10 NIM seats with forced-dissent iteration and treated the
Opus seat as if it were a cheap parallel call. An independent Opus adversarial
review of that draft found: two of the "9 reviewers" resolved to the exact same
underlying model (zero epistemic diversity), and the 3-4-round design would have
spent the Opus session-quota escalation 3-4x per plan, conflicting with the
repo's own 1-per-task rule. This design replaces it.

A second Opus adversarial review (2026-08-12), run specifically against a
proposal to make the taxonomy/format stricter, found the strict-format proposal
would have silently degraded already-weak NIM output (from zero verified
findings to zero *parseable* findings) and that a per-category finding quota
would incentivize fabrication — both fixed as described above before landing.

## Related

- `.claude/rules_db/dqiii8-plan-gate.md` — the single-Opus-escalation rule this reuses
- `quality-gate` skill — code-level checks; this is plan-level, runs earlier
- `audit` skill — same tracked-report-path pattern
