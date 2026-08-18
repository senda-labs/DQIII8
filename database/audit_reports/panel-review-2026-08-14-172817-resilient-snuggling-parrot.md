# Panel Review — /root/.claude/plans/resilient-snuggling-parrot.md

Opus seat spends the operator's own Claude Code session quota (OAuth, no ANTHROPIC_API_KEY configured) — it reuses the existing single-escalation allowance from dqiii8-plan-gate.md, not an additional budget.

**SEAT DEGRADED — epistemic diversity lost:**
- python-specialist: intended nim/deepseek-ai/deepseek-v4-flash, actually served by groq/llama-3.3-70b-versatile
- data-specialist: intended nim/mistralai/mistral-large-3-675b-instruct-2512, actually served by groq/llama-3.3-70b-versatile
Treat NIM seat findings as fewer independent opinions than the seat count implies while this holds.

## python-specialist — API/contract correctness, test coverage
provider=groq model=llama-3.3-70b-versatile status=ok latency_ms=2483
(no verified findings)

<details><summary>10 dropped finding(s) (unverifiable citation — shown, not deleted)</summary>

- [fake_path] \## Security: considered, no issues found.
\## Correctness: 
[CATEGORY: Correctness] [SEVERITY: P1]
/root/dqiii8/metadata_remove.py:106-121
The `inspect()` function does not handle encrypted or corrupt PDFs, leading to false success reports.
- [fake_path] [CATEGORY: Correctness] [SEVERITY: P2]
/root/dqiii8/fmt_image.py:250-309
The JPEG pure-Python fallback emits the SOS segment twice, producing an undecodable output.
- [fake_path] [CATEGORY: Correctness] [SEVERITY: P2]
/root/dqiii8/fmt_image.py:112,144,161-167
The XMP tags are never detected due to a mismatch in the identity check.
- [fake_path] [CATEGORY: Correctness] [SEVERITY: P2]
/root/dqiii8/fmt_pdf.py:216-220
The PDF safe tier destroys all embedded file attachments, not just C2PA manifests.
- [fake_path] [CATEGORY: Correctness] [SEVERITY: P2]
/root/dqiii8/metadata_remove.py:56-80
TIFF findings are marked as removable, but the `_transform` function does not support TIFF.
- [fake_path] \## DataIntegrity: considered, no issues found.
\## Resilience: 
[CATEGORY: Resilience] [SEVERITY: P2]
/root/dqiii8/safeio.py:100-124
The `safeio.iter_files` function does not handle truncation correctly, leading to invisible errors in `--json` output.
- [fake_path] [CATEGORY: Resilience] [SEVERITY: P2]
/root/dqiii8/metadata_remove.py:119
The `removable` status is applied uniformly to docProps findings, regardless of subtype.
- [fake_path] \## Operational: 
[CATEGORY: Operational] [SEVERITY: P2]
/root/dqiii8/metadata_purge_backups.py:69-70
The path-matching logic uses raw string equality, leading to mismatches between relative and absolute paths.
- [fake_path] [CATEGORY: Operational] [SEVERITY: P3]
/root/dqiii8/metadata_audit.py:186-187
The JSON report silently drops the `unreadable` skip counter.
- [fake_path] [CATEGORY: Operational] [SEVERITY: P3]
/root/dqiii8/tests/test_metadata_no_write_audit.py:20
The denylist matches only `remove_`/`clean_`-prefixed names, missing actual entrypoints.
</details>

## data-specialist — data integrity, blast radius, rollback/undo path
provider=groq model=llama-3.3-70b-versatile status=ok latency_ms=2987
(no verified findings)

<details><summary>10 dropped finding(s) (unverifiable citation — shown, not deleted)</summary>

- [fake_path] [DataIntegrity: Data Integrity] [SEVERITY: P0]
metadata_lib/safeio.py:53-77 
The `atomic_replace` function does not properly handle symlinks, allowing for arbitrary file writes.
Exploit/failure scenario: An attacker creates a dangling symlink to a sensitive file, and the `atomic_replace` function overwrites the contents of that file.
- [fake_path] [DataIntegrity: Data Integrity] [SEVERITY: P0]
watermark_remove.py:118-136 
The `watermark_remove` function does not properly handle symlinks, allowing for arbitrary file writes.
Exploit/failure scenario: An attacker creates a dangling symlink to a sensitive file, and the `watermark_remove` function overwrites the contents of that file.
- [fake_path] [DataIntegrity: Data Integrity] [SEVERITY: P1]
fmt_image.py:46-141 
The `exiftool_available` function may return incorrect results if the exiftool executable is not on the system's PATH.
Exploit/failure scenario: An attacker removes the exiftool executable from the system's PATH, causing the `exiftool_available` function to return incorrect results.
- [fake_path] [DataIntegrity: Data Integrity] [SEVERITY: P1]
fmt_image.py:112,144,161-167 
The `_list_tags_via_exiftool` function does not properly handle XMP tags, causing them to be silently ignored.
Exploit/failure scenario: An attacker embeds XMP tags in an image file, and the `_list_tags_via_exiftool` function fails to detect them.
- [fake_path] [DataIntegrity: Data Integrity] [SEVERITY: P1]
fmt_pdf.py:216-220 
The `fmt_pdf` function may delete non-C2PA manifests, causing data loss.
Exploit/failure scenario: An attacker embeds a non-C2PA manifest in a PDF file, and the `fmt_pdf` function deletes it.
- [fake_path] [DataIntegrity: Data Integrity] [SEVERITY: P1]
metadata_remove.py:106-121 
The `metadata_remove` function may report false success when encountering encrypted or corrupt PDFs.
Exploit/failure scenario: An attacker creates an encrypted or corrupt PDF file, and the `metadata_remove` function reports that it was successfully processed.
- [fake_path] [Resilience: Resilience] [SEVERITY: P2]
safeio.py:100-124 
The `iter_files` function may truncate files without warning, causing data loss.
Exploit/failure scenario: An attacker uses the `iter_files` function to process a large file, and the function truncates the file without warning.
- [fake_path] [Resilience: Resilience] [SEVERITY: P2]
audit_log.py:31 
The `audit_log` function does not properly handle file opens, allowing for potential data corruption.
Exploit/failure scenario: An attacker creates a file with a symlink to a sensitive location, and the `audit_log` function overwrites the contents of that file.
- [fake_path] [Operational: Operational] [SEVERITY: P3]
metadata_purge_backups.py:69-70 
The `metadata_purge_backups` function may not properly handle path matching, causing potential data loss.
Exploit/failure scenario: An attacker creates a file with a relative path, and the `metadata_purge_backups` function fails to match it with the corresponding absolute path.
- [no_citation] [Operational: Operational] [SEVERITY: P3]
report.py 
The `report` function may not properly handle JSON output, causing potential data loss.
Exploit/failure scenario: An attacker uses the `report` function to generate a JSON report, and the function fails to include important information.
</details>

## safety-checker — destructive-operation and permission review
provider=nim model=nvidia/llama-3.1-nemoguard-8b-content-safety status=error latency_ms=64885
error: [dqiii8.__main__] WARNING circuit open for nim — skipping provider (cooldown 120s)
[dqiii8.__main__] WARNING nim failed — trying next...
[dqiii8.__main__] WARNING groq/llama-3.3-70b-versatile attempt 1/3 failed — retrying in 1.1s
[dqiii8.__main__] WARNING groq/llama-3.3-70b-versatile attempt 2/3 failed — retrying in 2.0s
[dqiii8.__main__] WARNING groq failed — trying next...
[dqiii8.__main__] WARNING openrouter/qwen/qwen3-coder fatal error (auth/config) — not retrying
[dqiii8.__main__] WARNING circuit OPEN for openrouter (14 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING openrouter failed — trying next...
[dqiii8.__main__] WARNING github/deepseek-v3-0324 fatal error (auth/config) — not retrying
[dqiii8.__main__] WARNING circuit OPEN for github (13 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING github failed — trying next...
[dqiii8.__main__] WARNING pollinations/openai attempt 1/3 failed — retrying in 1.2s
[dqiii8.__main__] WARNING pollinations/openai attempt 2/3 failed — retrying in 2.1s
[dqiii8.__main__] WARNING circuit OPEN for pollinations (13 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING pollinations failed — trying next...
[dqiii8.__main__] ERROR all providers failed
(no verified findings)

## code-reviewer — adversarial (Opus, single pass)
provider=anthropic model=claude-opus-4-8 status=ok latency_ms=232224

- [Security] [P3] [CATEGORY: Security] [SEVERITY: P3]
bin/tools/metadata_lib/safeio.py:63 — fix 1's diagnosis is mis-scoped
The plan claims safeio's `.tmp` open is exploitable and "just needs `O_NOFOLLOW` added," but line 63 already passes `O_CREAT|O_EXCL`, which fails `EEXIST` on any pre-existing symlink (dangling or not) — so safeio's `.tmp` is not the hole. The genuinely unprotected writes are `watermark_remove.py:128` (`bak.write_bytes`) and `watermark_remove.py:133` (`tmp.write_text`, no `O_EXCL`).
Exploit/failure scenario: an implementer trusting the plan hardens safeio (already safe on `.tmp`) and treats watermark_remove as merely "reusing the primitive"; if the consolidation is deferred, the dangling-`.tmp` → symlinked-file bug the plan describes still lives in watermark_remove.py, unpatched.
- [Correctness] [P2] [CATEGORY: Correctness] [SEVERITY: P2]
bin/tools/metadata_lib/fmt_pdf.py:89 — fix 5 reconstructs a typed enum from a display string
The note is built as `f"{e.error_class.label}: {e.message}"`; fix 5 recovers the `ErrorClass` by re-parsing that string. Structured data round-tripped through human-facing text is fragile and drives the process exit code.
Exploit/failure scenario: a future `MetadataToolError` message beginning with a colon-prefixed token, or a label rename, makes the split resolve the wrong `ErrorClass` — an `adversarial` (exit 3) input silently downgraded to `corrupt` (exit 1), the exact masking the taxonomy exists to prevent. The Finding should carry the `ErrorClass` object, not a formatted string.
- [DataIntegrity] [P2] [CATEGORY: DataIntegrity] [SEVERITY: P2]
bin/tools/metadata_lib/fmt_pdf.py:216-220 — fix 4 under-specifies the destructive fix
The bug (unconditional `del pdf.Root.AF` / `del names.EmbeddedFiles`) is real, but `/AF` is a Root array and `/EmbeddedFiles` a name-tree under `/Names`; "only remove entries among `manifest_objs`" requires surgical pruning the plan never details, and it omits the tier of the new non-manifest Finding.
Exploit/failure scenario: manifest objects are already gutted in place at fmt_pdf.py:206-214, so a partial-pruning implementation that still touches the name-tree can corrupt the `/Names` structure of a Factur-X invoice; or, if the new Finding lands as `safe`+`removable=True`, the same attachment destruction simply re-occurs behind a finding.
- [Resilience] [P3] [CATEGORY: Resilience] [SEVERITY: P3]
bin/tools/watermark_remove.py:133 — fix 1 and fix 13 mutate the same function in different batches
Fix 1 (critical batch) re-routes this write path onto safeio's bytes primitive; fix 13 (high batch) fixes its UTF-16→UTF-8 corruption. Sequencing them apart means the post-critical-batch state can bake UTF-16 content through a UTF-8-assuming shared path before fix 13 lands.
Exploit/failure scenario: per-batch pytest passes after the critical batch on ASCII fixtures, hiding that a UTF-16 file is now silently transcoded; the interaction is never asserted because the two fixes' tests live in separate batches.
- [Operational] [P2] [CATEGORY: Operational] [SEVERITY: P2]
.claude/rules/00_core_behavior.md:21-27 — verification protocol violates the kernel's absolute cost rule
The plan's Verification section mandates a second Opus Workflow adversarial re-review. The Cost-First Rule ("absolute") and INVARIANTE-NIM ("non-negotiable... OBLIGATORIO intentar NIM primero") forbid reaching Tier S without exhausting NIM. The plan invokes CLAUDE.md governance selectively — it adopts the `/panel-review` mandate but ignores the co-equal cost mandate.
Exploit/failure scenario: "no resource constraint" (a user aside) is treated as overriding a kernel rule labeled absolute/non-negotiable; the re-review burns Opus tokens for a diff-scoped check `panel-review`'s NIM seats + one Opus pass already cover, normalizing Cost-First bypass.

## Verdict
Union of all verified findings above, Opus findings weighted highest. This is a report, not a gate — the operator/session is responsible for addressing each finding before implementation.