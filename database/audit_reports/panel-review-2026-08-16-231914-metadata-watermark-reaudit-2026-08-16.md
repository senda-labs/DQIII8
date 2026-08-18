# Panel Review — .claude/plans/metadata-watermark-reaudit-2026-08-16.md

Opus seat spends the operator's own Claude Code session quota (OAuth, no ANTHROPIC_API_KEY configured) — it reuses the existing single-escalation allowance from dqiii8-plan-gate.md, not an additional budget.

**SEAT DEGRADED — epistemic diversity lost:**
- python-specialist: intended nim/deepseek-ai/deepseek-v4-flash-0731, actually served by groq/llama-3.3-70b-versatile
- data-specialist: intended nim/nvidia/llama-3.3-nemotron-super-49b-v1.5, actually served by groq/llama-3.3-70b-versatile
- safety-checker: intended nim/nvidia/llama-3.1-nemoguard-8b-content-safety, actually served by groq/llama-3.3-70b-versatile
Treat NIM seat findings as fewer independent opinions than the seat count implies while this holds.

## python-specialist — API/contract correctness, test coverage
provider=groq model=llama-3.3-70b-versatile status=ok latency_ms=3235
(no verified findings)

## data-specialist — data integrity, blast radius, rollback/undo path
provider=groq model=llama-3.3-70b-versatile status=ok latency_ms=2438
(no verified findings)

<details><summary>8 dropped finding(s) (unverifiable citation — shown, not deleted)</summary>

- [fake_path] [DataIntegrity: Data Integrity] [SEVERITY: P2]
audit_log.py:31
The log file is opened without O_NOFOLLOW, which could lead to a potential security vulnerability if the log file is a symlink.
Exploit/failure scenario: An attacker could create a symlink to a sensitive file, and the log file would be written to that file, potentially causing data corruption or information disclosure.
- [no_citation] [Resilience: Resilience] [SEVERITY: P2]
metadata_remove.py: 
The tool does not disclose whether it ran the degraded engine, which could lead to confusion about the effectiveness of the metadata removal.
Exploit/failure scenario: An operator may not realize that the tool used a degraded engine, which could lead to incomplete metadata removal, potentially causing data integrity issues.
- [no_citation] [DataIntegrity: Data Integrity] [SEVERITY: P2]
metadata_remove.py: 
The tool never discloses that it ran the degraded engine, which could lead to confusion about the effectiveness of the metadata removal.
Exploit/failure scenario: An operator may not realize that the tool used a degraded engine, which could lead to incomplete metadata removal, potentially causing data integrity issues.
- [no_citation] [Resilience: Resilience] [SEVERITY: P2]
fmt_ooxml.py: 
The tool claims to remove metadata, but it does not actually remove it for xlsx/pptx files, which could lead to incomplete metadata removal.
Exploit/failure scenario: An operator may think that the tool has removed all metadata, but some metadata may still be present, potentially causing data integrity issues.
- [no_citation] [DataIntegrity: Data Integrity] [SEVERITY: P2]
metadata_audit.py: 
The tool does not handle truncated sweeps correctly, which could lead to incorrect results.
Exploit/failure scenario: An operator may think that the tool has completed a sweep, but it may have been truncated, potentially causing incorrect results.
- [no_citation] [Resilience: Resilience] [SEVERITY: P2]
metadata_purge_backups.py: 
The tool uses raw string equality to match paths, which could lead to incorrect matching.
Exploit/failure scenario: An operator may think that the tool has purged the correct backups, but it may have missed some or purged incorrect ones, potentially causing data integrity issues.
- [no_citation] [DataIntegrity: Data Integrity] [SEVERITY: P2]
fmt_image.py: 
The tool does not detect or remove JPEG COM segments, which could lead to incomplete metadata removal.
Exploit/failure scenario: An operator may think that the tool has removed all metadata, but some metadata may still be present in the JPEG COM segment, potentially causing data integrity issues.
- [no_citation] [Resilience: Resilience] [SEVERITY: P2]
watermark_remove.py: 
The tool claims to remove watermarks, but it does not actually remove them if every write was refused, which could lead to confusion about the effectiveness of the watermark removal.
Exploit/failure scenario: An operator may think that the tool has removed the watermark, but it may still be present, potentially causing data integrity issues.
</details>

## safety-checker — destructive-operation and permission review
provider=groq model=llama-3.3-70b-versatile status=ok latency_ms=1617
(no verified findings)

<details><summary>6 dropped finding(s) (unverifiable citation — shown, not deleted)</summary>

- [no_citation] [Operational: destructive ops/permission scope] [SEVERITY: P2]
bin/tools/metadata_lib/fmt_ooxml.py: 
Inconsistent implementation of removable findings for different document types.
- [no_citation] [Operational: destructive ops/permission scope] [SEVERITY: P2]
metadata_audit.py: 
No handling of truncated sweeps, which can lead to inaccurate reports.
- [no_citation] [Operational: destructive ops/permission scope] [SEVERITY: P2]
metadata_remove.py: 
No disclosure of whether the operation was performed using the degraded engine.
- [fake_path] [Operational: destructive ops/permission scope] [SEVERITY: P3]
audit_log.py:31: 
Log file opened without O_NOFOLLOW, which could lead to a security vulnerability.
- [no_citation] [Operational: destructive ops/permission scope] [SEVERITY: P2]
watermark_remove.py: 
Incorrect reporting of removal success when writes are refused.
- [no_citation] [Operational: destructive ops/permission scope] [SEVERITY: P2]
metadata_purge_backups.py: 
Legacy relative entries may not match correctly, leading to accumulation of backups.
</details>

## code-reviewer — adversarial (Opus, single pass)
provider=anthropic model=claude-opus-4-8 status=timeout latency_ms=360000
(no verified findings)

**Opus seat returned zero verified findings** — this is the rare, informative signal (cheap seats returning nothing is the observed baseline and not itself noteworthy). Treat as an actual clean bill only after confirming the Opus seat had real repo access and did not time out/error.

## Verdict
Union of all verified findings above, Opus findings weighted highest. This is a report, not a gate — the operator/session is responsible for addressing each finding before implementation.