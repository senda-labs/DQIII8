---
name: panel-review
description: Adversarial review of a plan file — a single Opus pass — before implementation of a ≥3-module or ambiguous-scope change.
command: /panel-review
allowed-tools: [Bash, Read]
user-invocable: true
---

# /panel-review — Plan Adversarial Review

Run before implementing any plan that touches ≥3 modules or has ambiguous scope,
after plan-mode design and before writing code.

## Usage

```
/panel-review <plan-file>
```

Runs `python3 bin/tools/panel_review.py <plan-file>`.

## What it does

**INV2 (2026-08-18)**: this used to run 3 heterogeneous NIM seats as a $0
breadth-first pre-filter alongside the Opus pass. Under the user's
2026-08-18 Anthropic-only directive (no non-Anthropic provider API is
operative today), those seats would route through dead infrastructure —
removed rather than kept as a pre-filter that silently returns nothing every
run. If the multi-tier chain is ever reactivated
(`.claude/rules_db/archive/multi-tier-dormant-2026-08.md`), re-adding a
pre-filter is a deliberate future decision, not an automatic revert of this
one.

1. **Exactly ONE Opus adversarial pass** (`code-reviewer` agent → `claude-opus-4-8`),
   the entire review. **This spends the operator's own Claude Code session
   quota** — no `ANTHROPIC_API_KEY` is configured, so it runs as a nested
   `claude -p` OAuth call. It reuses the *existing* single-Opus-escalation
   allowance defined in `.claude/rules_db/dqiii8-plan-gate.md` (max 1 per task) —
   it is not an additional or second Opus budget. No iteration, no forced
   dissent, no re-voting loop: one pass, one verdict. It reads the plan and
   the repo and must cite `file:line` for every finding — uncited findings
   are discarded by the orchestrator, not just flagged.
2. **Report**: written to `database/audit_reports/panel-review-YYYY-MM-DD-HH-<slug>.md`.
   **Never committed — policy set 2026-08-18.** `database/audit_reports/*.md` is fully
   gitignored, no negation. (History: a 2026-08-17 design briefly tracked these reports
   via a narrow `.gitignore` negation — reverted 2026-08-18 after that negation was found
   to leave a report containing a real infra IP + a Postgres credential literal one
   `git add -A` away from being staged, the same failure class the negation was meant to
   prevent for `docs/audits/` in the first place.) Durability for these reports comes
   from the off-VPS backup channels documented in `CLAUDE.md` (`backup_audit_docs.sh` +
   `telegram_audit_backup.py`), not from git. `.gitleaks.toml` still carries the
   `audit-docs-bare-ipv4` / `audit-docs-password-literal` rules scoped to this corpus —
   now mostly a defense-in-depth backstop against a future re-negation, but still worth
   running (`gitleaks detect`) over any new report as a manual habit, since these files
   never pass through the pre-commit hook at all while gitignored.
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

One extra safeguard survives INV2's single-seat redesign:
- **"All clean" flag**: the report calls out a zero-verified-findings result
  explicitly, rather than letting it read the same as "not shown" — the Opus
  pass returning nothing is rare and actually means something.

(The pre-INV2 design also carried a seat-degradation banner comparing
intended vs actual provider/model per seat, and gated "all clean" on the
**Opus** seat specifically among several. Both no longer apply with a single
seat and no NIM fallback path — see "Why this design (history)" below.)

There is deliberately no "find at least one issue per category" quota — on a
seat that has already fabricated a citation once (observed live: invented
`src/db.py:15` in a repo with no `src/` directory), a quota is a fabrication
incentive, not a rigor increase.

## Hardening from enterprise-grade stress testing (2026-08-12)

Live adversarial testing of `panel_review.py` (and the sibling `watermark_scan.py`
pre-commit check) against real crafted payloads, not hypothetical ones, found and
fixed 4 real bugs in the citation/parsing path:

- **Citation path escaped `REPO_ROOT`**: `/etc/passwd:1` and
  `../../../etc/passwd:1` both resolved and "verified" — `Path`'s `/` operator
  discards the left operand entirely for an absolute right-hand operand, so the
  intended repo-scoping silently didn't happen. Fixed: `_citation_exists()`
  rejects any path starting with `/` or `~` outright, then requires
  `candidate.is_relative_to(REPO_ROOT.resolve())` before treating a match as real.
- **ReDoS in `CITATION_RE`**: a ~200KB adversarial non-matching block hung the
  parser >120s (confirmed quadratic backtracking, not exponential, via a
  doubling-input timing sweep). Fixed with `MAX_BLOCK_LEN = 3000`: blocks past
  that length can't be a legitimate finding anyway (real findings are short,
  ~4-line structured blocks) and are dropped with reason `block_too_long`
  *before* ever reaching the regex — never silently discarded, still shown in
  the dropped-findings appendix.
- **Markdown/HTML structure injection**: finding text originates from an LLM
  response, itself shaped by the plan-under-review (untrusted input). Unsanitized
  text could forge a fake `## Verdict` heading or close the report's `<details>`
  block early, visually spoofing the real verdict for whoever reads the report.
  Fixed with `_sanitize_for_report()`, applied at parse time: escapes leading
  `#` headings, `</details>`, `<details`, `<summary`, `<script`.
- **Hook exit-code swallowing**: `.git/hooks/pre-commit` had no `set -e`, so a
  failing `gitleaks protect` followed by a passing `watermark_scan.py` returned
  exit 0 overall — silently defeating the secret-blocking gate. Fixed by adding
  `set -e` to both the live hook and `bin/tools/setup_gitleaks_hook.sh` (so
  re-provisioning doesn't reintroduce it).

`watermark_scan.py` got 3 companion fixes in the same pass: it now scans the
**staged git index blob** (`git cat-file -p :<path>`) instead of the working-tree
file (closes a stage-then-revert-without-restaging bypass), skips staged
symlinks entirely (a symlink's blob content is the target path string, not the
target file's content — following it would scan the wrong thing), and reads
staged filenames via `git diff --cached ... -z` instead of the default
C-quoted output (closes a silent skip of any staged file with a non-ASCII name).

**Known residual limitation, disclosed rather than fixed**: `_citation_exists()`
only proves the cited `file:line` exists in this repo — it does not verify the
finding's actual *claim* is really about that file/line. A seat could cite a
real, unrelated file to make a fabricated defect look verified. Judged
disproportionate to fix (would require semantic verification of claim-to-code
correspondence, a much heavier mechanism) relative to the residual risk, given
Opus's findings are weighted highest and a human (the calling CC session) reads
every verified finding before acting on it. Not silently assumed safe — recorded
here as an open gap.

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
