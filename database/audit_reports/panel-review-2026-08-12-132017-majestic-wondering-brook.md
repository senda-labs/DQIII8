# Panel Review — /root/.claude/plans/majestic-wondering-brook.md

Opus seat spends the operator's own Claude Code session quota (OAuth, no ANTHROPIC_API_KEY configured) — it reuses the existing single-escalation allowance from dqiii8-plan-gate.md, not an additional budget.

**SEAT DEGRADED — epistemic diversity lost:**
- python-specialist: intended nim/deepseek-ai/deepseek-v4-flash, actually served by groq/llama-3.3-70b-versatile
- safety-checker: intended nim/nvidia/llama-3.1-nemoguard-8b-content-safety, actually served by groq/llama-3.3-70b-versatile
Treat NIM seat findings as fewer independent opinions than the seat count implies while this holds.

## python-specialist — API/contract correctness, test coverage
provider=groq model=llama-3.3-70b-versatile status=ok latency_ms=1899
(no verified findings)

## data-specialist — data integrity, blast radius, rollback/undo path
provider=nim model=mistralai/mistral-large-3-675b-instruct-2512 status=error latency_ms=65309
error: [dqiii8.__main__] WARNING circuit open for nim — skipping provider (cooldown 120s)
[dqiii8.__main__] WARNING nim failed — trying next...
[dqiii8.__main__] WARNING groq/llama-3.3-70b-versatile attempt 1/3 failed — retrying in 1.1s
[dqiii8.__main__] WARNING groq/llama-3.3-70b-versatile attempt 2/3 failed — retrying in 2.2s
[dqiii8.__main__] WARNING groq failed — trying next...
[dqiii8.__main__] WARNING openrouter/qwen/qwen3-coder fatal error (auth/config) — not retrying
[dqiii8.__main__] WARNING circuit OPEN for openrouter (4 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING openrouter failed — trying next...
[dqiii8.__main__] WARNING github/deepseek-v3-0324 fatal error (auth/config) — not retrying
[dqiii8.__main__] WARNING circuit OPEN for github (3 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING github failed — trying next...
[dqiii8.__main__] WARNING pollinations/openai attempt 1/3 failed — retrying in 1.1s
[dqiii8.__main__] WARNING pollinations/openai attempt 2/3 failed — retrying in 2.1s
[dqiii8.__main__] WARNING circuit OPEN for pollinations (3 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING pollinations failed — trying next...
[dqiii8.__main__] ERROR all providers failed
(no verified findings)

## safety-checker — destructive-operation and permission review
provider=groq model=llama-3.3-70b-versatile status=ok latency_ms=2237
(no verified findings)

<details><summary>5 dropped finding(s) (unverifiable citation — shown, not deleted)</summary>

- [no_citation] \### Correctness: 
[CATEGORY: Correctness] [SEVERITY: P2]
/root/dqiii8/bin/tools/health_check.py
one-line defect description: The `health_check.py` script has a maskable penalty that could be improved for staleness check.
Exploit/failure scenario: If the staleness check fails, the penalty could be masked by other checks, leading to a false sense of security.
- [no_citation] \### DataIntegrity: 
[CATEGORY: DataIntegrity] [SEVERITY: P1]
/root/dqiii8/bin/tools/db_backup.sh
one-line defect description: The `db_backup.sh` script has a rotation glob that matches its own sidecars, consuming retention slots.
Exploit/failure scenario: This could lead to data loss if the backup retention slots are filled with sidecars, causing the script to delete important backups.
- [no_citation] \### Resilience: 
[CATEGORY: Resilience] [SEVERITY: P2]
/root/dqiii8/bin/monitoring/health_watchdog.py
one-line defect description: The `health_watchdog.py` script fails 6 out of 8 checks due to bugs, not real failures.
Exploit/failure scenario: This could lead to a false sense of security, as the script is not accurately reporting the system's health.
- [no_citation] \### Operational: 
[CATEGORY: Operational] [SEVERITY: P1]
/root/dqiii8/bin/tools/health_check.py
one-line defect description: The `health_check.py` script has a hardcoded alert threshold that may not be suitable for all scenarios.
Exploit/failure scenario: This could lead to unnecessary alerts or failures to alert in critical situations, impacting the system's operability.
- [no_citation] [CATEGORY: Operational] [SEVERITY: P2]
/root/dqiii8/bin/core/notify.py
one-line defect description: The `send_telegram()` function never raises an exception, but its result is not checked, potentially leading to silent failures.
Exploit/failure scenario: If the `send_telegram()` function fails, the error will not be logged or reported, making it difficult to detect and respond to issues.
</details>

## code-reviewer — adversarial (Opus, single pass)
provider=anthropic model=claude-opus-4-8 status=ok latency_ms=157632

- [Correctness] [P1] **[CATEGORY: Correctness] [SEVERITY: P1]**
`bin/monitoring/health_watchdog.py:77-83` (plan item **1a** / "decision #4")
The plan's flagship premise is false against current code. Item 1a asserts "every entry in the `{name: Path}` dict shares one staleness `limit`, which is wrong for `auto_researcher.py`" and proposes restructuring the dict to `(Path, cadence)` tuples. But `check_crons()` **already** special-cases it: line 78 is `limit = 192 if name == "auto_researcher" else 48` (8-day grace), with the intent spelled out in the line-77 comment. Worse, the "precondition cannot be met — fires `log file missing` daily until 2026-08-17" concern is a *missing-file* failure at line 72-73 (`if not log_path.exists()`), which short-circuits **before** any age/limit logic (lines 75-82) ever runs.
Exploit/failure scenario: An implementer builds the cadence-aware limit exactly as specified. It changes nothing about the stated blocker: `/tmp/dqiii8_researcher.log` is absent, so line 72 fires `False, "log file missing"` regardless of a 192h vs 168h limit. The "reach 0 failures before Stage 1" gate still can't be met, the refactor risks regressing the already-correct 192h path, and a decision the plan marks "resolved" is resolved against a misread of the file it claims to have "directly read."
- [Correctness] [P2] **[CATEGORY: Correctness] [SEVERITY: P2]**
`bin/monitoring/health_watchdog.py:34` + `bin/tools/health_check.py:108` (plan item **4**, heartbeat dead-man's-switch)
The watchdog writes `NOW.isoformat()` where `NOW` is timezone-**aware** UTC (line 34, `datetime.now(timezone.utc)`), producing `...+00:00`. `health_check.py` imports only `from datetime import datetime` (line 20) and uses **naive** `datetime.now()` throughout (line 108). The plan tells `health_check.py` to "parse as ISO-8601 ... notify() if missing or >24h stale" inside its own try/except.
Exploit/failure scenario: The natural implementation computes `datetime.now() - datetime.fromisoformat(hb)` → `TypeError: can't subtract offset-naive and offset-aware datetimes`. The plan wraps this block in a per-block try/except (its own words), so the exception is swallowed silently. The health_check→watchdog half of the dead-man's-switch never alerts and produces no log line — recreating exactly the silent-no-op failure class (NEW-4) this plan exists to close. Zero of the eight verification scenarios exercises a real aware-heartbeat write consumed by naive `health_check.py`.
- [Operational] [P3] **[CATEGORY: Operational] [SEVERITY: P3]**
`bin/tools/db_backup.sh:4` (plan item **3**, `check_backup_log`)
The plan reads backup health from `/tmp/dqiii8_db_backup.log` (the cron redirect at line 4). It carefully protects the heartbeat from `/tmp` boot-wipe in item 4 ("`/tmp` is emptied at boot") but applies no such reasoning to this equally `/tmp`-backed log.
Exploit/failure scenario: VPS reboots at 08:00. `/tmp/dqiii8_db_backup.log` is wiped; the next backup isn't until 05:00 the following day. For ~21h `check_backup_log` fires "file missing" on a perfectly healthy backup chain — a fresh cry-wolf source added by the very plan whose stated goal is to stop cry-wolf.

<details><summary>3 dropped finding(s) (unverifiable citation — shown, not deleted)</summary>

- [fake_path] **Security:** considered, no issues found. Test invocations blank all three token vars; `notify.py:18` `load_dotenv` non-override is correctly accounted for; DB reads are read-only (`health_check.py:31`) and queries are constant/parameterized — no injection, no hardcoded secrets introduced.
- [fake_path] **DataIntegrity:** considered, no issues found. Rotation sorts ISO-timestamp filenames lexicographically = chronologically (`db_backup.sh:71-72`); the one-time sidecar deletion is correctly gated on explicit user approval.
- [fake_path] **Resilience:** one acknowledged residual, not a hidden defect. The watchdog still performs production writes every run — `check_auto_learner --consolidate` (`health_watchdog.py:90-101`) and `save_exchange` (`health_watchdog.py:186-202`) — so the "run once in production to seed the heartbeat" deploy note mutates prod as a side effect of a diagnostic. The plan explicitly defers this rather than ignoring it, so it's a scoping choice, not an unflagged hazard.
</details>

## Verdict
Union of all verified findings above, Opus findings weighted highest. This is a report, not a gate — the operator/session is responsible for addressing each finding before implementation.