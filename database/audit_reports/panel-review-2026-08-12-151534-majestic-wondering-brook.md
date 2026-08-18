# Panel Review — /root/.claude/plans/majestic-wondering-brook.md

Opus seat spends the operator's own Claude Code session quota (OAuth, no ANTHROPIC_API_KEY configured) — it reuses the existing single-escalation allowance from dqiii8-plan-gate.md, not an additional budget.

## python-specialist — API/contract correctness, test coverage
provider=nim model=deepseek-ai/deepseek-v4-flash status=error latency_ms=61514
error: [dqiii8.__main__] WARNING nim/deepseek-ai/deepseek-v4-flash fatal error (auth/config) — not retrying
[dqiii8.__main__] WARNING circuit OPEN for nim (25 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING nim failed — trying next...
[dqiii8.__main__] WARNING groq/llama-3.3-70b-versatile fatal error (auth/config) — not retrying
[dqiii8.__main__] WARNING groq failed — trying next...
[dqiii8.__main__] WARNING openrouter/qwen/qwen3-coder fatal error (auth/config) — not retrying
[dqiii8.__main__] WARNING circuit OPEN for openrouter (6 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING openrouter failed — trying next...
[dqiii8.__main__] WARNING github/deepseek-v3-0324 fatal error (auth/config) — not retrying
[dqiii8.__main__] WARNING circuit OPEN for github (5 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING github failed — trying next...
[dqiii8.__main__] WARNING pollinations/openai attempt 1/3 failed — retrying in 1.0s
[dqiii8.__main__] WARNING pollinations/openai attempt 2/3 failed — retrying in 2.2s
[dqiii8.__main__] WARNING circuit OPEN for pollinations (5 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING pollinations failed — trying next...
[dqiii8.__main__] ERROR all providers failed
(no verified findings)

## data-specialist — data integrity, blast radius, rollback/undo path
provider=nim model=mistralai/mistral-large-3-675b-instruct-2512 status=error latency_ms=521
error: [dqiii8.__main__] WARNING circuit open for nim — skipping provider (cooldown 120s)
[dqiii8.__main__] WARNING nim failed — trying next...
[dqiii8.__main__] WARNING groq/llama-3.3-70b-versatile fatal error (auth/config) — not retrying
[dqiii8.__main__] WARNING groq failed — trying next...
[dqiii8.__main__] WARNING circuit open for openrouter — skipping provider (cooldown 120s)
[dqiii8.__main__] WARNING openrouter failed — trying next...
[dqiii8.__main__] WARNING circuit open for github — skipping provider (cooldown 120s)
[dqiii8.__main__] WARNING github failed — trying next...
[dqiii8.__main__] WARNING circuit open for pollinations — skipping provider (cooldown 120s)
[dqiii8.__main__] WARNING pollinations failed — trying next...
[dqiii8.__main__] ERROR all providers failed
(no verified findings)

## safety-checker — destructive-operation and permission review
provider=nim model=nvidia/llama-3.1-nemoguard-8b-content-safety status=error latency_ms=476
error: [dqiii8.__main__] WARNING circuit open for nim — skipping provider (cooldown 120s)
[dqiii8.__main__] WARNING nim failed — trying next...
[dqiii8.__main__] WARNING groq/llama-3.3-70b-versatile fatal error (auth/config) — not retrying
[dqiii8.__main__] WARNING circuit OPEN for groq (3 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING groq failed — trying next...
[dqiii8.__main__] WARNING circuit open for openrouter — skipping provider (cooldown 120s)
[dqiii8.__main__] WARNING openrouter failed — trying next...
[dqiii8.__main__] WARNING circuit open for github — skipping provider (cooldown 120s)
[dqiii8.__main__] WARNING github failed — trying next...
[dqiii8.__main__] WARNING circuit open for pollinations — skipping provider (cooldown 120s)
[dqiii8.__main__] WARNING pollinations failed — trying next...
[dqiii8.__main__] ERROR all providers failed
(no verified findings)

## code-reviewer — adversarial (Opus, single pass)
provider=anthropic model=claude-opus-4-8 status=ok latency_ms=155369

- [Correctness] [P2] **[CATEGORY: Correctness] [SEVERITY: P2]**
`bin/monitoring/health_watchdog.py:80-81`
`check_crons()` still hard-fails a missing log file, while the plan's own post-reboot `/tmp`-wipe reasoning was applied only to `check_backup_log` (`:281-289`, returns OK when absent). The same `/tmp`-backed logs (`/tmp/dqiii8_decay.log`, `/tmp/dqiii8_sandbox.log`, `/tmp/dqiii8_researcher.log`) drive `check_crons`.
Exploit/failure scenario: any VPS reboot wipes `/tmp`; `check_crons` then fires `cron:memory_decay/sandbox_tester/auto_researcher = "log file missing"` every 06:00 run until each cron next executes — up to 7 days for the weekly `auto_researcher`. The rail built to remove cry-wolf produces daily false alerts, and the plan's stated "reach 0 failures before Stage 1" gate silently cannot hold after a reboot.
- [DataIntegrity] [P2] **[CATEGORY: DataIntegrity] [SEVERITY: P2]**
`bin/tools/db_backup.sh:71`
The rotation glob excludes `-wal`/`-shm`/`.partial` but not names with a non-timestamp suffix. Any `${db}.bak-<nonnumeric>` file (e.g. `dqiii8.db.bak-manual`) is included, and because `sort -r` is lexical, a leading non-digit (`m` > `2`) sorts it *ahead* of every real `YYYYMMDD…` backup — so it is treated as newest and permanently kept.
Exploit/failure scenario: a botched restore or a human dropping one `dqiii8.db.bak-manual` file permanently consumes a `KEEP=7` slot; rotation then evicts a genuine daily backup one cycle early, silently dropping real retention from 7 to 6 — the exact "glob eats retention slots" class NEW-1 claims to have closed, left only half-fixed.
- [Operational] [P2] **[CATEGORY: Operational] [SEVERITY: P2]**
`bin/monitoring/health_watchdog.py:97-115` and `:197-214`
The monitoring rail mutates production on every daily run: `check_auto_learner` executes `auto_learner.py --consolidate --db dqiii8.db`, and `check_working_memory` calls `save_exchange('watchdog_test_001','ping','pong',…)` writing a real row into the production session store. The plan defers this ("production-write flag") indefinitely rather than fixing it.
Exploit/failure scenario: the observer perturbs the observed — a consolidation bug or a lock during 06:00 consolidate can corrupt/stall the live DB and is *caused by the health check itself*; and the store accrues a synthetic `watchdog_test_001` session daily forever, contaminating any query over session_memory. A monitor that writes to prod can manufacture the very failure it is meant to detect.
- [Resilience] [P3] **[CATEGORY: Resilience] [SEVERITY: P3]**
`bin/monitoring/health_watchdog.py:260-262`
`check_backup_span` requires `span_h >= (count-1)*20`, assuming exactly-daily backups. A single legitimate manual backup on the same calendar day as a cron backup compresses total span below the threshold once `count` reaches `BACKUP_MIN_RETAIN`.
Exploit/failure scenario: operator runs `db_backup.sh` manually after a change, so two of the kept backups share a day; span falls under `(count-1)*20h` and the watchdog fires `"backups present but not aged — possible burst restore"` against a perfectly healthy chain — a new false positive on the de-noising rail.

<details><summary>1 dropped finding(s) (unverifiable citation — shown, not deleted)</summary>

- [fake_path] **Security: considered, no issues found.** Token is read only from env (`notify.py:73-77`), backup paths are fully script-derived with no user input (no shell/SQL injection surface), and DB opens are read-only URIs. The `settings.json` SPOF (#2) and gitleaks checksum (Stage 2/3) are unbuilt future work, not defects in the code I read.
</details>

## Verdict
Union of all verified findings above, Opus findings weighted highest. This is a report, not a gate — the operator/session is responsible for addressing each finding before implementation.