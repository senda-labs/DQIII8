# Metadata / Watermark Toolchain — Independent Re-Audit and Remediation

Date: 2026-08-16
Scope: `bin/tools/metadata_audit.py`, `metadata_remove.py`, `metadata_purge_backups.py`,
`watermark_scan.py`, `watermark_audit.py`, `watermark_remove.py`,
`bin/tools/metadata_lib/*`, `tests/test_metadata_*.py`, `tests/test_watermark_scan.py`.

## Why this report exists

The 2026-08-14 panel produced 53 findings (8 critical / 20 high / 17 medium / 8 low).
Both the approved plan (`.claude/plans/resilient-snuggling-parrot.md`) and the full
53-item list were never committed and are permanently lost. The only surviving artifact
is `database/audit_reports/panel-review-2026-08-14-172817-resilient-snuggling-parrot.md`,
which contains 20 `[fake_path]`-dropped leads from the two NIM seats plus 5 verified
Opus findings.

This re-audit does not attempt to recover the lost list. It re-derives coverage from
scratch: every one of the 20 surviving leads is adjudicated against the current code,
the 5 Opus fixes are re-verified by reading the code rather than trusting prior notes,
and an independent adversarial sweep looks for what the panel may have missed.

**Every verdict below rests on observed tool output against real artifacts**, not on
code reading alone. A test bench was built for this purpose containing a JPEG with
EXIF/GPS/XMP/COM, a PNG, a WebP, a TIFF, a PDF, a Factur-X-style PDF carrying a real
business-data attachment beside a C2PA manifest, a DOCX, an XLSX and a PPTX (the last
two authored with `creator = Iker Martins` so a false clean is directly observable).

A note on provenance: this toolchain removes *file-level* metadata and *invisible
Unicode characters embedded in file bytes*. It is unrelated to Anthropic's statistical
text watermark (announced 2026-08-11, green/red token bias) — that one is a property of
generated token distributions and is not addressed, or addressable, by any tool here.

---

## Part 1 — The 20 surviving leads, one by one

Citations in the leads point at paths that do not exist in this repo
(`/root/dqiii8/fmt_image.py` etc. — the real files live under
`bin/tools/metadata_lib/`), which is why the orchestrator dropped all 20 as
`fake_path`. A wrong path does not make the underlying claim wrong, so each was
adjudicated on substance against the real file. **Line numbers cited below are the
current ones, verified today — not the leads' numbers.**

`P-n` = python-specialist seat, `D-n` = data-specialist seat.

| # | Lead (substance) | Verdict | Evidence in current code |
|---|---|---|---|
| P-1 | `inspect()` mishandles encrypted/corrupt PDFs → false success | **ALREADY FIXED** | `fmt_pdf.py` raises `MetadataToolError` carrying an `ErrorClass`; `metadata_remove.py` maps it via `cls = engine_error.error_class or ErrorClass.ENGINE_FAILURE`. An encrypted PDF exits 2 (`ENCRYPTED_OR_SIGNED`), never 0. Verified by running an encrypted PDF through `--apply`. |
| P-2 | JPEG pure-Python fallback emits SOS twice → undecodable output | **ALREADY FIXED** | `fmt_image.py:384` — `out += raw[_last_scan_offset(raw):]`, with `_last_scan_offset()` defined at `fmt_image.py:429`. Fallback-stripped JPEG re-decodes and is pixel-identical. |
| P-3 | XMP tags never detected (identity-check mismatch) | **ALREADY FIXED** | `fmt_image.py:169` `_is_identity_group()` matches `group.startswith("XMP-")`; called at `:218`. A `XMP-dc:Creator` tag is reported. |
| P-4 | PDF safe tier destroys *all* embedded attachments, not just C2PA | **ALREADY FIXED** | Opus fix 3. `_is_c2pa_filespec()` (`fmt_pdf.py:86`) + `_prune_name_tree()` (`:131`, used `:366`) prune surgically; non-manifest attachments become a `removable=False` finding. Verified: the Factur-X payload bytes survive a safe-tier clean that removes the C2PA manifest. |
| P-5 | TIFF marked removable but `_transform` has no TIFF path | **ALREADY FIXED** | `fmt_image.py:186` — `removable = fmt != "tiff"`, plus an explanatory note. |
| P-6 | Truncated sweep is invisible in `--json` | **REAL — fixed in this pass (F2)** | `metadata_audit.scan_directory` printed the cap message to stderr and discarded it; `--json` had no `truncated` key and exit was 0. |
| P-7 | `removable` applied uniformly to docProps regardless of subtype | **REAL — fixed in this pass (F1)** | See reproduction below. |
| P-8 | Purge path-matching uses raw string equality | **REAL — fixed in this pass (F4)** | `metadata_purge_backups.py:69` — `if e.get("path") != str(target)`. |
| P-9 | JSON report silently drops the `unreadable` skip counter | **REAL — fixed in this pass (F3)** | `metadata_audit.report()` merged with `if k in summary.skipped`; `report.Summary.skipped` has no `unreadable` key. |
| P-10 | No-write denylist matches only `remove_`/`clean_` prefixes | **ALREADY FIXED** | `tests/test_metadata_no_write_audit.py:24` `_write_capable_symbols()` derives the set and explicitly includes bare `remove`; `:83` asserts it. |
| D-1 | `atomic_replace` mishandles symlinks → arbitrary write | **FALSE** | `safeio.py:71` refuses a symlinked target and a pre-existing/symlinked `.bak`; the `.tmp` open at `:43` uses `O_CREAT\|O_EXCL\|O_NOFOLLOW`. Opus itself corrected this same mis-scoping in its finding 1. |
| D-2 | `watermark_remove` symlink → arbitrary write | **ALREADY FIXED** | Opus fix 1. Both `.bak` and `.tmp` go through `write_new_file()`; `watermark_remove.py:160`. Verified: a pre-planted symlink is refused, not followed. |
| D-3 | `exiftool_available` wrong if exiftool not on PATH | **FALSE** | `fmt_image.py:34` pins `EXIFTOOL_PATH = "/usr/bin:/bin"` and `:54` resolves against it. Absence is reported as `degraded`, never silently assumed present. |
| D-4 | duplicate of P-3 | **ALREADY FIXED** | as P-3 |
| D-5 | duplicate of P-4 | **ALREADY FIXED** | as P-4 |
| D-6 | duplicate of P-1 | **ALREADY FIXED** | as P-1 |
| D-7 | duplicate of P-6 | **REAL (F2)** | as P-6 |
| D-8 | `audit_log` opens the log without `O_NOFOLLOW` | **REAL — fixed in this pass (F9)** | `audit_log.py:31`. |
| D-9 | duplicate of P-8 | **REAL (F4)** | as P-8 |
| D-10 | `report.py` "may not handle JSON output correctly" (no citation) | **UNVERIFIABLE AS STATED** | Too vague to adjudicate. Its only concrete substance overlaps P-9, which is real and fixed. |

**Tally:** 20 lead entries → 7 flag real defects (P-6, P-7, P-8, P-9, D-7, D-8, D-9),
which reduce to **5 distinct real defects** after de-duplication. 10 entries describe
defects that were already fixed, 2 are false, 1 is unverifiable.

Read as a signal about the lost 53: the two cheap seats' dropped output was
*substantively* ~35% accurate despite 100% of its citations being fabricated. The
citations were worthless; the claims were not.

---

## Part 2 — Re-verification of the 5 Opus fixes

Re-verified by reading the current code, as instructed — not from prior notes.

| Fix | Claim | Status |
|---|---|---|
| 1 | `watermark_remove`'s unprotected `bak.write_bytes` / `tmp.write_text` re-routed through the hardened primitive | **INTACT.** `watermark_remove.py:149-165` — both `.bak` and `.tmp` go through `write_new_file()` (`O_WRONLY\|O_CREAT\|O_EXCL\|O_NOFOLLOW`, mode 0o600), then `os.replace(tmp, path)`. Verified live: pre-planted `.tmp` symlink → refused. |
| 2 | `Finding` must carry the `ErrorClass` object, not a re-parsed display string | **INTACT.** `report.py:37` `error_class: ErrorClass \| None = None`; `:41` serialises `.label`. `fmt_pdf.inspect` passes `error_class=e.error_class`. No string round-trip remains; `grep` finds no re-parse of the `"label: message"` form. |
| 3 | `/AF` + `/Names/EmbeddedFiles` need surgical pruning, and the new non-manifest Finding must not be `safe`+`removable=True` | **INTACT.** `fmt_pdf.py:86,131,244-252,351,366`. The non-manifest attachment Finding is `removable=False`. Verified end-to-end on the Factur-X bench PDF: manifest gone, invoice payload bytes still readable, `/Names` tree still valid to pikepdf. |
| 4 | UTF-16 → UTF-8 corruption in `watermark_remove` | **INTACT.** `watermark_remove.py:55` `_encode_like_input()` preserves the BOM and re-encodes UTF-16-LE/BE in kind; used at `:160`. Verified on a real UTF-16-LE file: BOM and encoding survive a clean. |
| 5 | The plan's mandated *second* Opus re-review violates the kernel's absolute Cost-First rule | **HELD (process finding, not code).** No second-Opus re-review step exists in the toolchain or its docs. See the disclosure in "Process notes" below regarding this pass. |

All five hold. Fix 3 is the one worth restating: it is the difference between a
privacy tool and a data-loss tool, and the bench confirms real invoice data survives.


---

## Part 3 — Independent adversarial sweep: new findings

These are mine, not the panel's. They came from reading the toolchain against the
threat classes the brief named (symlink/TOCTOU, path traversal, exit codes and
error taxonomy, silent truncation, docs-vs-behaviour drift) rather than from any
surviving lead.

| ID | Severity | Finding | Why it matters |
|---|---|---|---|
| **F5** | **P0 (data exposure)** | A JPEG **COM segment (0xFFFE)** was detected by neither engine. exiftool buckets it under the catch-all `File` group, which `_is_identity_group` rejects; the pure-Python fallback's marker walker never listed `0xFFFE` among the droppable markers. | The COM segment is free text and routinely carries author names and authoring-tool strings. A JPEG carrying one was reported **clean** and survived `--apply`. A privacy tool reporting a false clean is worse than no tool. |
| **F6** | **P1 (false success)** | `watermark_remove` collapsed "wrote nothing because there was nothing to do" and "wanted to write and was refused" into one boolean. An unreadable file was an entirely invisible skip. | A run in which *every* write was blocked (pre-planted `.bak`, symlinked `.tmp`, permissions) printed a normal summary and **exited 0**. Any caller gating on exit status would conclude the clean succeeded. |
| **F2** | **P1 (silent truncation)** | The `MAX_DIR_FILES` cap was announced only on stderr. It never reached the JSON report and never changed the exit code, in all three sweeping tools. | A sweep that stopped after N files with no findings so far was byte-for-byte indistinguishable, to any machine consumer, from a complete clean sweep. |
| **F1** | **P1 (false promise)** | `fmt_ooxml.inspect` advertised `removable=True` for **xlsx and pptx**, but `metadata_remove._transform` implements docx only and raises `UNSUPPORTED` for everything else. | The dry run promised a removal `--apply` could never perform. Worse, the resulting status `no_target_tier_findings` is in `SUCCESS_STATUSES`, so the failure was silent. |
| **F7** | **P2 (undisclosed degradation)** | `metadata_remove` did not report engine versions or degradation. With exiftool absent it silently fell back to the narrower pure-Python remover. | `metadata_audit` disclosed degradation; `metadata_remove` — the tool that actually mutates files — did not. The operator could not tell which engine cleaned their files. |
| **F3** | **P2 (report integrity)** | `report()` merged skip counts through a preset-key filter, silently dropping any reason not in the template (e.g. `unreadable`). | Files that were never examined vanished from the JSON entirely, again indistinguishable from a clean scan. |
| **F4** | **P2 (correctness)** | `metadata_remove` logged `str(path)` as given, and `metadata_purge_backups` matched log entries by raw string equality. | A removal run from one cwd and a purge run from another never matched, so `.bak` files containing the *original, uncleaned* metadata were left on disk indefinitely — the opposite of the tool's purpose. |
| **F9** | **P2 (symlink)** | `audit_log.append` opened the log path without `O_NOFOLLOW` and chmod'd by path. | A symlink planted at the log path redirected appends into a victim file, and the path-based chmod could be raced. |

### Deferred, with reasons (see Part 5)
**F8** (exit code `2` overloaded) and **F10** (image XMP provenance detection gap).

---

## Part 4 — What was fixed, and how each fix was verified

All eight fixes were implemented. Nothing here is called "resolved" on the strength
of pytest alone; every entry has end-to-end evidence against real artifacts on the
bench (`shot.jpg`, `shot.png`, `shot.webp`, `shot.tiff`, `base.pdf`, a Factur-X
`invoice.pdf` with a C2PA manifest, `doc.docx`, `book.xlsx`, `deck.pptx`).

| Fix | Change | End-to-end evidence |
|---|---|---|
| F5 | `fmt_image.inspect` gates on the **tag** (`tag == "Comment"`), never the group; fallback walker emits a `jpeg_comment` Finding for `0xFFFE`; `remove()` appends `-Comment=` **only for jpeg**; `0xFFFE` added to `drop_markers`. | Real JPEG with a planted COM: audit now reports `JPEG:COM`; `--apply` removes it; payload bytes absent from the output; image still decodes in Pillow. |
| F6 | `remove_from_file` returns `(findings, written, refused)`. The three genuine refusal families return `refused=True`; dry run / out-of-tier / no-op return `False`. `main()` accumulates refusals, reworded the summary to separate *eligible* from *rewrote*, and exits `5 → 1 → 0`. | Symlinked `.tmp` planted: run now prints the refusal and **exits 1**. Negative runs confirmed a dry run and a clean file still exit **0**. |
| F2 | `EXIT_TRUNCATED = 5` in all three tools; `scan_directory`/`collect_files` return the truncation reason; `build_report` emits `"truncated"`; precedence stated explicitly: **truncated (5) > degraded (2) > findings (1) > clean (0)**. | Verified by patching `MAX_DIR_FILES` **in-process** (see the correction note below): exit 5, `"truncated"` present in the JSON. |
| F1 | `fmt_ooxml.inspect` rewrites findings to `removable=False` with an explanatory note for any subtype other than docx. Applied at the call site, not inside `detect_xmp_provenance()`, which the PDF path shares. Plus a `--apply` disclosure block naming files that still carry findings. | `book.xlsx` / `deck.pptx` audits now show `removable=false` and the note; `doc.docx` still shows `removable=true` and still cleans. |
| F7 | `metadata_remove` imports `_engine_versions`, emits `engines` + `degraded` in `--json`, and prints a `DEGRADED` line in text mode. | Run with exiftool monkeypatched absent: the degradation line appears and `degraded` is populated in the JSON. |
| F3 | Skip counts are **merged, never filtered**. | An `unreadable` count now survives into `summary.skipped` in the emitted JSON. |
| F4 | `metadata_remove` logs `str(path.resolve())`; `_path_matches` resolves **absolute** entries only and leaves legacy relative entries on raw string equality. | Purge from an unrelated cwd now matches; a legacy relative entry provably does **not** bind to the purge run's cwd. |
| F9 | `os.open(..., O_APPEND \| O_NOFOLLOW, 0o600)` + `fchmod` on the held fd. | Symlink planted at the log path: append refused with a warning, victim file byte-identical, **no exception raised** — and a real clean still completes and exits 0 with the log unavailable. |

### Test coverage added

`tests/test_metadata_reaudit_2026_08_16.py` — **19 tests**, one or more per fix,
including seven deliberately *negative* tests that pin the direction in which each
fix could break something.

**These tests were mutation-verified, not merely observed green.** Each fix was
reverted in a scratch copy of `bin/tools/` and the suite re-run; every fix has at
least one test that fails against the pre-fix code. Three mutation rounds, 14
distinct reversals, all caught. Notably:

- Reverting F5's jpeg-conditional into an unconditional `-Comment=` in the shared
  `_SAFE_CLEAR_ARGS` fails `test_png_text_chunk_is_not_touched_by_safe_tier_removal`
  — this is the **P0 that the adversarial review caught in my own plan** before any
  code was written, now permanently pinned by a test.
- Reverting F4 to raw string equality fails the absolute-path match test, while the
  legacy-relative negative test still passes — confirming the fix is genuinely
  additive and does not change behaviour for old log entries.

**Full suite: 537 tests, 536 passed, 1 skipped, exit 0.** No regressions (baseline
was 518 before this pass).

---

## Part 5 — Remaining technical debt, and why none of it blocks

Recorded rather than fixed. Each has an explicit reason.

| ID | Debt | Why not now |
|---|---|---|
| **F8** | Exit code `2` is overloaded: it means both *degraded engines* and *usage error* (bad `--dir`/`--file`). A caller cannot distinguish them from the status alone. | Fixing it means renumbering a published exit contract, which would silently break any existing caller that already branches on 2 — a larger blast radius than the ambiguity itself. The precedence is now **documented in code** at the top of `metadata_audit.py`, so the ambiguity is disclosed rather than latent. Revisit if/when the contract is versioned. |
| **F10** | Image **XMP provenance** detection is narrower than the PDF path's. XMP embedded in JPEG/WebP is detected as XMP but not parsed for provenance-specific fields the way `detect_xmp_provenance()` does for PDFs. | This is a *coverage gap*, not a false clean: the XMP block is still detected, still reported, and still removed by both engines. Closing it is a detection-enrichment task with its own test corpus, not a correctness fix. |
| — | `audit_log.append` has **no locking** for concurrent appends. | Single writes are small and `O_APPEND` on Linux is atomic below `PIPE_BUF` for regular files in practice; the tool is explicitly human-invoked and never wired into CI or hooks, so genuine concurrency is not a real workflow today. Adding `flock` would be cheap but is unjustified without a concurrent caller to justify it. |
| — | The AST **no-write denylist** guarding `metadata_audit.py` checks a fixed set of write primitives. A novel write path (e.g. via `shutil`, or an indirect call) would not be caught. | The existing denylist covers every write primitive the file actually could reach today, and the test fails loudly if a listed one appears. Widening it to a general allowlist-based proof is a materially different (and much stricter) mechanism; the current one is a real guard, just not a proof. |

None of these can produce a **false clean** — which is the failure mode this
toolchain exists to prevent, and the bar I used to decide what had to be fixed in
this pass.

---

## Part 6 — Process notes (disclosed, not buried)

Three things about how this audit was conducted that a reader is entitled to know.

**1. The `/panel-review` gate was honoured, and it produced no usable signal.**
The fix set touches ≥3 modules, so per `CLAUDE.md` and `00_core_behavior.md` the
plan (`.claude/plans/metadata-watermark-reaudit-2026-08-16.md`) went through
`/panel-review` before any code was written. The run
(`database/audit_reports/panel-review-2026-08-16-231914-…`) came back with:

- a **SEAT DEGRADED banner** — all three supposedly heterogeneous NIM seats were
  served by the same `groq/llama-3.3-70b-versatile`, exactly the failure mode the
  skill documents (and consistent with the account-level NIM 403 recorded in
  `00_core_behavior.md` as of today);
- **zero verified findings**, and 14 dropped findings that merely paraphrased my
  own plan back at me;
- `code-reviewer … status=timeout latency_ms=360000` — **the Opus seat never ran**.

Per the skill's own guidance, cheap seats finding nothing is the baseline, not a
clean bill. I did not treat it as one.

**2. I substituted a real adversarial pass, and it found a P0 in my own plan.**
Because the Opus seat timed out, I ran a `feature-dev:code-reviewer` (Opus) pass
against the plan directly. It found that my F5 as drafted would have added
`-Comment=` to the **shared** `_SAFE_CLEAR_ARGS`, destroying `--all`-tier PNG
tEXt/iTXt data during a plain safe-tier `--apply` — a data-loss bug in the fix for
a data-exposure bug. It also found F4's justification factually wrong, F1's failure
mode silent, and F6's discriminator undefined. All four were corrected in the plan
before implementation. **This is the single highest-value event in the audit**, and
it happened only because the gate was not skipped when the automated run degenerated.

*In tension with:* the 2026-08-14 Opus finding 5 (Cost-First: no second Opus pass).
Stated plainly — this was **one** Opus pass in total, standing in for the one the
gate was supposed to run and didn't. It is not a second escalation on top of a
successful first one. But it was a judgement call I made, not a rule the repo
already granted, and it is recorded here as such rather than presented as routine.

**3. A correction to an earlier verification of my own.**
An initial truncation "reproduction" set `MAX_DIR_FILES=1` as a shell environment
variable. That is **invalid** — `MAX_DIR_FILES` is a module constant and is never
read from the environment, so the run proved nothing. The authoritative verification
patches the constant **in-process**, and that is what yields exit 5. Recording the
retraction because a verification that does not verify is worse than none.

---

---

## Part 7 — F11: the report path is gitignored (P0, process; flagged, not fixed)

Found while writing this report, and it is the most important finding in it.

```
$ git check-ignore -v database/audit_reports/2026-08-16-metadata-watermark-toolchain-reaudit.md
.gitignore:192:database/audit_reports/   database/audit_reports/...

$ git ls-files database/audit_reports/ | wc -l
0
$ ls database/audit_reports/ | wc -l
127
```

**`database/audit_reports/` is ignored wholesale. All 127 audit reports in this repo
— including this one — are untracked.** One `git clean -fdx` destroys every one of
them.

This is precisely the mechanism that lost the 53-finding list this audit exists to
replace. The `panel-review` skill documents that failure in its own text ("Never
`docs/superpowers/` — that path is gitignored, which is exactly how a prior review's
findings ledger was permanently lost") and then names
`database/audit_reports/` as the safe, **tracked** alternative
(`.claude/skills/panel-review/SKILL.md:39`). That claim is false. The skill directs
its output to a path with the same defect it was written to avoid — textbook
docs-versus-real-behaviour drift, which is one of the categories this sweep was asked
to cover.

**Deliberately not fixed in this pass, and flagged for a human decision instead.**
Un-ignoring the directory would stage 127 existing files at once, and their contents
are not audited for secrets — `analytics.log` sits in the same directory, and this
repo has a documented history of credential leaks to a public remote (Telegram token,
2026-08-06; Netcup IP + root SSH command, 2026-08-13). Reversing a `.gitignore` rule
that currently withholds 127 unreviewed files from a public repository is exactly the
kind of change that must not be made autonomously as a side effect of an unrelated
audit.

**Recommended (needs an explicit decision):**
1. Decide whether audit reports belong in git at all, or in a separate backed-up store.
2. If in git: negate narrowly (`!database/audit_reports/*.md`), keep `analytics.log`
   and `archive/` ignored, and run `gitleaks` over the 127 files **before** the first
   commit — not after.
3. Either way, correct `.claude/skills/panel-review/SKILL.md:39`, which currently
   asserts a guarantee the repo does not provide.

Until this is resolved, **this report is as unrecoverable as the list it replaces.**


## Closing

Of the 20 surviving leads, **5 distinct real defects** remained (7 entries,
de-duplicated). All five are fixed. My own sweep added **three more** (F5, F6, F7),
one of them a P0 false-clean, plus the truncation gap extended across all three
sweeping tools. All five prior Opus fixes were re-verified against current code and
hold. Two findings are deferred as documented debt, neither capable of producing a
false clean.

The lost 53-item list is not recovered and cannot be. What this pass provides
instead is equivalent coverage reached independently: every surviving lead
adjudicated against real code with runtime evidence, plus a fresh adversarial sweep
that found defects the panel did not. That is the strongest available substitute,
and it should be treated as superseding the lost list rather than as a partial
reconstruction of it.
