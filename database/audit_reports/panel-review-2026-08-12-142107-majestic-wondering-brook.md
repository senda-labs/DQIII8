# Panel Review — /root/.claude/plans/majestic-wondering-brook.md

Opus seat spends the operator's own Claude Code session quota (OAuth, no ANTHROPIC_API_KEY configured) — it reuses the existing single-escalation allowance from dqiii8-plan-gate.md, not an additional budget.

**SEAT DEGRADED — epistemic diversity lost:**
- python-specialist: intended nim/deepseek-ai/deepseek-v4-flash, actually served by groq/llama-3.3-70b-versatile
- safety-checker: intended nim/nvidia/llama-3.1-nemoguard-8b-content-safety, actually served by groq/llama-3.3-70b-versatile
Treat NIM seat findings as fewer independent opinions than the seat count implies while this holds.

## python-specialist — API/contract correctness, test coverage
provider=groq model=llama-3.3-70b-versatile status=ok latency_ms=2571
(no verified findings)

<details><summary>7 dropped finding(s) (unverifiable citation — shown, not deleted)</summary>

- [fake_path] [CATEGORY: Correctness] [SEVERITY: P2]
/bin/monitoring/health_watchdog.py:72 
The `check_crons()` function short-circuits on a missing log file, preventing the staleness check from running.
- [fake_path] [CATEGORY: Correctness] [SEVERITY: P2]
/bin/tools/health_check.py:108 
The `datetime.now()` call is naive and may cause incorrect comparisons with aware datetimes.
- [fake_path] [CATEGORY: Correctness] [SEVERITY: P2]
/bin/core/notify.py:116 
The `send_telegram()` function never raises an exception on failure, and its result is discarded, potentially leading to silent failures.
- [no_citation] [CATEGORY: DataIntegrity] [SEVERITY: P0]
/root/dqiii8/database/backups/ 
The backup retention policy is silently set to 2 days instead of 7, potentially leading to data loss.
- [fake_path] [CATEGORY: DataIntegrity] [SEVERITY: P2]
/bin/tools/db_backup.sh:71 
The backup script does not correctly handle sidecar files, potentially leading to data corruption.
- [fake_path] [CATEGORY: Resilience] [SEVERITY: P1]
/bin/monitoring/health_watchdog.py:34 
The `health_watchdog.py` script fails 6 out of 8 checks, potentially leading to false negatives.
- [fake_path] [CATEGORY: Resilience] [SEVERITY: P2]
/bin/tools/health_check.py:110 
The `health_check.py` script does not correctly handle errors, potentially leading to silent failures.
</details>

## data-specialist — data integrity, blast radius, rollback/undo path
provider=nim model=mistralai/mistral-large-3-675b-instruct-2512 status=error latency_ms=64846
error: [dqiii8.__main__] WARNING circuit open for nim — skipping provider (cooldown 120s)
[dqiii8.__main__] WARNING nim failed — trying next...
[dqiii8.__main__] WARNING groq/llama-3.3-70b-versatile attempt 1/3 failed — retrying in 1.1s
[dqiii8.__main__] WARNING groq/llama-3.3-70b-versatile attempt 2/3 failed — retrying in 2.1s
[dqiii8.__main__] WARNING groq failed — trying next...
[dqiii8.__main__] WARNING openrouter/qwen/qwen3-coder fatal error (auth/config) — not retrying
[dqiii8.__main__] WARNING circuit OPEN for openrouter (5 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING openrouter failed — trying next...
[dqiii8.__main__] WARNING github/deepseek-v3-0324 fatal error (auth/config) — not retrying
[dqiii8.__main__] WARNING circuit OPEN for github (4 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING github failed — trying next...
[dqiii8.__main__] WARNING pollinations/openai attempt 1/3 failed — retrying in 1.0s
[dqiii8.__main__] WARNING pollinations/openai attempt 2/3 failed — retrying in 2.0s
[dqiii8.__main__] WARNING circuit OPEN for pollinations (4 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING pollinations failed — trying next...
[dqiii8.__main__] ERROR all providers failed
(no verified findings)

## safety-checker — destructive-operation and permission review
provider=groq model=llama-3.3-70b-versatile status=ok latency_ms=2349
(no verified findings)

<details><summary>2 dropped finding(s) (unverifiable citation — shown, not deleted)</summary>

- [fake_path] \## Operational: 
[OPERATIONAL: Destructive operations and permission review] [SEVERITY: P2]
/root/dqiii8/bin/tools/db_backup.sh:71 
The script uses a destructive operation (deletion of backup sidecar files) without explicit user approval, although approval is flagged as needed in the comments.
Exploit/failure scenario: The script could potentially delete important files if not properly configured or if the sidecar files are not properly identified.
- [no_citation] [OPERATIONAL: Destructive operations and permission review] [SEVERITY: P3]
/root/dqiii8/docs/audits/2026-08-12-disaster-scenario-stress-test.md 
The audit report does not explicitly state the permissions required for the corrective actions, which could lead to unauthorized access or changes.
Exploit/failure scenario: An unauthorized user could potentially gain access to sensitive information or make changes to the system if the permissions are not properly set.
</details>

## code-reviewer — adversarial (Opus, single pass)
provider=anthropic model=claude-opus-4-8 status=ok latency_ms=112551

- [Resilience] [P1] **[CATEGORY: Resilience] [SEVERITY: P1]**
bin/core/notify.py:118 (callers health_check.py:125,140,154,171)
`notify()` discards `send_telegram()`'s `SendResult` — on delivery failure it only `log.warning`s and returns `None`. The entire `health_check.py` alerting rail (score<70, heartbeat missing/stale, crash) routes through `notify()`, so none of it confirms delivery.
Exploit/failure scenario: the 2026-08-06 token-rotation event repeats → `send_telegram` returns `ok=False, error="missing_token_or_chat_id"` → both the score alert and the dead-man's-switch alerts silently no-op, nothing reaches Telegram, both rails read green. The watchdog got its result checked (health_watchdog.py:387) but `health_check.py` did not — an asymmetric fix that leaves the higher-value rail blind. Stage 1.1 #1 proposes only a breadcrumb; this is live *now*.
- [Resilience] [P2] **[CATEGORY: Resilience] [SEVERITY: P2]**
bin/tools/health_check.py:35 (block at 134-156, handler at 163-173)
The heartbeat dead-man's-switch lives inside `main()` and runs only on the successful path. `sqlite3.connect` at line 35 is *before* any try/except.
Exploit/failure scenario: `dqiii8.db` is locked/corrupt → line 35 raises → `__main__` catches, sends "health_check crashed", and never runs the heartbeat check — the one check built specifically to catch silent failures does not run on the exact failure class most likely to cause one. Plan flags this (Stage 1.1 #2) but it is unfixed in the code.
- [Resilience] [P2] **[CATEGORY: Resilience] [SEVERITY: P2]**
bin/tools/health_check.py:35; bin/monitoring/health_watchdog.py:143, :332
Read-only DB opens use short timeouts (health_check.py:35 default 5s; watchdog 143 and 332 `timeout=5`), directly violating project rule 01 ("always `timeout=30` — default 5s produces `SQLITE_BUSY` under parallel dispatch").
Exploit/failure scenario: a watchdog/health run coincides with a WAL checkpoint or parallel dispatch write → `SQLITE_BUSY` → `check_db_integrity`/`human_hours` fail and fire a false "DB integrity failed" alert — new cry-wolf noise on the rail this plan exists to de-noise.
- [Operational] [P2] **[CATEGORY: Operational] [SEVERITY: P2]**
bin/monitoring/health_watchdog.py:93-111 and :193-210
The "monitoring" rail mutates production on every run: `check_auto_learner` runs `auto_learner.py --consolidate` against the live DB, and `check_working_memory` calls `save_exchange(...)` writing `watchdog_test_001` rows into session memory.
Exploit/failure scenario: a monitoring check is expected to be side-effect-free; here a daily cron silently writes to prod, and the deploy-note run (`python3 health_watchdog.py` "to seed the heartbeat") also triggers a consolidation write as a side effect. Plan defers this ("production-write flag"), but shipping new checks onto a write-capable monitor is a standing hazard, not a resolved one.
- [DataIntegrity] [P3] **[CATEGORY: DataIntegrity] [SEVERITY: P3]**
bin/monitoring/health_watchdog.py:220
`BACKUP_MIN_RETAIN = 7 if date.today() >= date(2026, 8, 19) else 3` — the code flips on **08-19**, but the plan prose (Stage 1 item 2) claims "reaches 7 by 2026-08-16." Also, once `count >= 7` there is no oldest-backup-age assertion (Stage 1.1 #3, unlanded).
Exploit/failure scenario: a burst restore/reseed creating 7 same-timestamp backups passes `check_backup_freshness` identically to 7 genuine daily backups → the check reports a healthy 7-day retention window that does not exist.
- [Correctness] [P3] **[CATEGORY: Correctness] [SEVERITY: P3]**
bin/monitoring/health_watchdog.py:143
`check_db_integrity` opens the WAL DB read-**write** (`sqlite3.connect(str(DB), ...)`) while `check_human_hours` (line 332) correctly uses `file:{DB}?mode=ro`. A read-only check should not hold a write-capable handle.
Exploit/failure scenario: opening rw can trigger `-wal`/`-shm` creation or checkpoint contention against the live bot process during the check — same class of sidecar/lock side effect Stage 0.1 worked to eliminate for backups.

## Verdict
Union of all verified findings above, Opus findings weighted highest. This is a report, not a gate — the operator/session is responsible for addressing each finding before implementation.