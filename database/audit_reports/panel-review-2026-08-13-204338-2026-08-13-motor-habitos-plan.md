# Panel Review — docs/superpowers/plans/2026-08-13-motor-habitos-plan.md

Opus seat spends the operator's own Claude Code session quota (OAuth, no ANTHROPIC_API_KEY configured) — it reuses the existing single-escalation allowance from dqiii8-plan-gate.md, not an additional budget.

## python-specialist — API/contract correctness, test coverage
provider=nim model=deepseek-ai/deepseek-v4-flash status=error latency_ms=61630
error: [dqiii8.__main__] WARNING nim/deepseek-ai/deepseek-v4-flash fatal error (auth/config) — not retrying
[dqiii8.__main__] WARNING circuit OPEN for nim (33 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING nim failed — trying next...
[dqiii8.__main__] WARNING groq/llama-3.3-70b-versatile fatal error (auth/config) — not retrying
[dqiii8.__main__] WARNING circuit OPEN for groq (4 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING groq failed — trying next...
[dqiii8.__main__] WARNING openrouter/qwen/qwen3-coder fatal error (auth/config) — not retrying
[dqiii8.__main__] WARNING circuit OPEN for openrouter (13 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING openrouter failed — trying next...
[dqiii8.__main__] WARNING github/deepseek-v3-0324 fatal error (auth/config) — not retrying
[dqiii8.__main__] WARNING circuit OPEN for github (12 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING github failed — trying next...
[dqiii8.__main__] WARNING pollinations/openai attempt 1/3 failed — retrying in 1.1s
[dqiii8.__main__] WARNING pollinations/openai attempt 2/3 failed — retrying in 2.2s
[dqiii8.__main__] WARNING circuit OPEN for pollinations (12 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING pollinations failed — trying next...
[dqiii8.__main__] ERROR all providers failed
(no verified findings)

## data-specialist — data integrity, blast radius, rollback/undo path
provider=nim model=mistralai/mistral-large-3-675b-instruct-2512 status=error latency_ms=236
error: [dqiii8.__main__] WARNING circuit open for nim — skipping provider (cooldown 120s)
[dqiii8.__main__] WARNING nim failed — trying next...
[dqiii8.__main__] WARNING circuit open for groq — skipping provider (cooldown 120s)
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
provider=nim model=nvidia/llama-3.1-nemoguard-8b-content-safety status=error latency_ms=273
error: [dqiii8.__main__] WARNING circuit open for nim — skipping provider (cooldown 120s)
[dqiii8.__main__] WARNING nim failed — trying next...
[dqiii8.__main__] WARNING circuit open for groq — skipping provider (cooldown 120s)
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
provider=anthropic model=claude-opus-4-8 status=ok latency_ms=237089

- [Correctness] [P2] [CATEGORY: Correctness] [SEVERITY: P2]
`bin/tools/db_backup.sh:5`
Plan appends the habits-backup block into a script running `set -euo pipefail`; any un-`if`-guarded command in that block aborts the whole script before `exit "$((failures>0?1:0))"` (line ~89), bypassing the `failures` accounting the rest of the script relies on.
Exploit/failure scenario: cron (`50 2`) has no tty; if the plan's `gpg` symmetric-encrypt call omits `--batch`/`--passphrase-fd`, it exits non-zero. Under `set -e` that un-guarded failure kills the script with an opaque exit code instead of incrementing `failures` and continuing — the operator sees a hard abort, not the intended "habits backup failed, mains OK" signal.
- **DataIntegrity: considered, no issues found.**
*(Plan uses an isolated `database/habits.db` and does not touch `database/schema_v2.sql` (the SSOT) or `dqiii8.db`; `authorized()` at `bin/ui/dqiii8_bot.py:121` is fail-closed. New `^hab:` callback prefix does not collide with existing `^sat:` (2196) or `^hpt` (2199).)*

<details><summary>1 dropped finding(s) (unverifiable citation — shown, not deleted)</summary>

- [no_citation] [CATEGORY: Operational] [SEVERITY: P3]
`.gitignore:35` (and `.gitignore:41`)
Plan Task 1 Step 6 adds `database/habits.db` / `-wal` / `-shm` entries that are already covered by `database/*.db` (line 35), and all backup artifacts are already covered by `database/backups/` (line 41). The additions are dead no-op lines.
Exploit/failure scenario: no runtime failure — but it signals the plan author did not verify existing ignore coverage before claiming to "add" it, and dead entries invite future confusion about which pattern is authoritative. Cosmetic; drop the redundant lines.
</details>

## Verdict
Union of all verified findings above, Opus findings weighted highest. This is a report, not a gate — the operator/session is responsible for addressing each finding before implementation.