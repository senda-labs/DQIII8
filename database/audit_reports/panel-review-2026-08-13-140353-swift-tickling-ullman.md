# Panel Review — /root/.claude/plans/swift-tickling-ullman.md

Opus seat spends the operator's own Claude Code session quota (OAuth, no ANTHROPIC_API_KEY configured) — it reuses the existing single-escalation allowance from dqiii8-plan-gate.md, not an additional budget.

**SEAT DEGRADED — epistemic diversity lost:**
- python-specialist: intended nim/deepseek-ai/deepseek-v4-flash, actually served by groq/llama-3.3-70b-versatile
- data-specialist: intended nim/mistralai/mistral-large-3-675b-instruct-2512, actually served by groq/llama-3.3-70b-versatile
Treat NIM seat findings as fewer independent opinions than the seat count implies while this holds.

## python-specialist — API/contract correctness, test coverage
provider=groq model=llama-3.3-70b-versatile status=ok latency_ms=2655
(no verified findings)

<details><summary>2 dropped finding(s) (unverifiable citation — shown, not deleted)</summary>

- [fake_path] \## Resilience: 
[CATEGORY: Resilience] [SEVERITY: P2]
/root/dqiii8/docs/audits/2026-08-13-p2-redteam-review-round2-disaster-stress.md:728
Missing end-to-end smoke test for enqueueing a real job against a scratch DB.
Exploit/failure scenario: If the audit's test had been in place, it would have caught the issue with the async job queue before it caused problems.
- [no_citation] \## Operational: 
[CATEGORY: Operational] [SEVERITY: P3]
/root/dqiii8(docs/audits/2026-08-13-p2-redteam-review-round2-disaster-stress.md): 
No synthetic load is being generated against januskeys.es to test its resilience and performance under stress.
Exploit/failure scenario: If a large number of users were to access the site simultaneously, it could lead to performance issues or even crashes, which would impact the site's availability and user experience.
</details>

## data-specialist — data integrity, blast radius, rollback/undo path
provider=groq model=llama-3.3-70b-versatile status=ok latency_ms=5375
(no verified findings)

## safety-checker — destructive-operation and permission review
provider=nim model=nvidia/llama-3.1-nemoguard-8b-content-safety status=error latency_ms=65936
error: [dqiii8.__main__] WARNING circuit open for nim — skipping provider (cooldown 120s)
[dqiii8.__main__] WARNING nim failed — trying next...
[dqiii8.__main__] WARNING groq/llama-3.3-70b-versatile attempt 1/3 failed — retrying in 1.1s
[dqiii8.__main__] WARNING groq/llama-3.3-70b-versatile attempt 2/3 failed — retrying in 2.0s
[dqiii8.__main__] WARNING groq failed — trying next...
[dqiii8.__main__] WARNING openrouter/qwen/qwen3-coder fatal error (auth/config) — not retrying
[dqiii8.__main__] WARNING circuit OPEN for openrouter (11 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING openrouter failed — trying next...
[dqiii8.__main__] WARNING github/deepseek-v3-0324 fatal error (auth/config) — not retrying
[dqiii8.__main__] WARNING circuit OPEN for github (10 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING github failed — trying next...
[dqiii8.__main__] WARNING pollinations/openai attempt 1/3 failed — retrying in 1.0s
[dqiii8.__main__] WARNING pollinations/openai attempt 2/3 failed — retrying in 2.2s
[dqiii8.__main__] WARNING circuit OPEN for pollinations (10 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING pollinations failed — trying next...
[dqiii8.__main__] ERROR all providers failed
(no verified findings)

## code-reviewer — adversarial (Opus, single pass)
provider=anthropic model=claude-opus-4-8 status=ok latency_ms=170149
(no verified findings)

<details><summary>6 dropped finding(s) (unverifiable citation — shown, not deleted)</summary>

- [fake_path] [CATEGORY: Correctness] [SEVERITY: P1]
`jobs/tasks.py` (proposed reconciliation task) vs `app/gateway/service.py:531`
Step 1.3 specifies the reconciliation sweep as `mir_submissions WHERE status='pending' AND deadline < now()`, but the code it claims to satisfy says the opposite: `# mir_submissions WHERE status='pending' AND deadline > now()`.
Exploit/failure scenario: A reservation loses its broker handoff (defer_async fails, durable pending row written per service.py:530-544). The plan's sweep selects `deadline < now()` — only rows already past their 24h legal window. Those re-enqueue into `submit_compliance`, which at tasks.py:207 (`if now >= deadline`) immediately DLQs them without sending. Meanwhile the still-valid pending rows (`deadline > now()`, the ones actually recoverable) are never re-enqueued. Result: compliance is never filed for exactly the guests it still legally can be — INVARIANT-3 broken, and the "fix" reports green.
- [fake_path] [CATEGORY: Correctness] [SEVERITY: P2]
`jobs/dlq.py:20`
Step 1.4 asserts `_SWEEP_SQL` "selects from a nonexistent `procrastinate_jobs` table; point it at the real table name." `procrastinate_jobs` *is* the canonical Procrastinate table name — created by the schema Step 1.1 installs. It is absent only because no schema is applied yet, not misnamed.
Exploit/failure scenario: A maintainer follows the instruction literally and renames the query to some invented "real" name, breaking a currently-correct query the moment the schema lands.
- [fake_path] [CATEGORY: Security] [SEVERITY: P1]
`docs/runbooks/00-signing-key-escrow.md:30-34` vs plan Step 3
Step 3 claims to "execute the existing runbook stub" but does the opposite: it `gpg --encrypt`s `hostkey.env` to the *same* public key used for DB backups and uploads it to the *same* B2 bucket. The runbook mandates `gpg --symmetric` with a passphrase stored in a *different* location from the blob, across 2+ locations.
Exploit/failure scenario: Compromise of that single GPG private key (or the B2 bucket) yields both the DB dumps and the Ed25519 signing key + PII master key together — total loss of key separation, the exact catastrophe the runbook's split design prevents.
- [no_citation] [CATEGORY: DataIntegrity] [SEVERITY: P2]
Plan Step 1 (rollback clause) vs its own verify step
The rollback claims the Procrastinate migration is "additive… `alembic downgrade -1` cleanly removes it." But the same Step 1 verify enqueues a *real* job through the worker.
Exploit/failure scenario: If Step 1 is rolled back after verification (or after any live job is deferred), `downgrade -1` drops `procrastinate_jobs`/`procrastinate_events` with queued compliance/revocation rows inside — silent loss of in-flight legal filings, not the clean no-op advertised.
- [fake_path] [CATEGORY: Resilience] [SEVERITY: P2]
`jobs/dlq.py:16-27` vs `jobs/tasks.py:168-173`
Two writers hit `dead_letter_jobs` with different column sets: dlq.py inserts `(original_job_id, queue, task_name, args, error_detail)`; tasks.py inserts `(queue, task_name, args, error_detail)` — no `original_job_id`. Step 1.5's smoke test only asserts enqueue→`succeeded`; it never exercises either DLQ path.
Exploit/failure scenario: If `original_job_id` is NOT NULL in the new schema, tasks.py's deadline-DLQ insert (tasks.py:220) throws, and the "never silent" DLQ (INVARIANT-2/-3) fails on the first missed compliance deadline — undetected, because the plan's only test is the happy path.
- [fake_path] [CATEGORY: Operational] [SEVERITY: P2]
`scripts/ops/deploy_hostkey_netcup.sh:17` vs plan Step 7.2 / 7.6
Step 7.2 attributes the 874MB of `.bak-*` accumulation to the missing rsync `--delete`. It isn't: line 17 `cp -a '${REMOTE_DIR}' '${REMOTE_DIR}.bak-${STAMP}'` creates a new sibling backup every run, outside all synced subdirs — `--delete` (which only prunes *within* `app/jobs/security/alembic/scripts`) cannot touch them.
Exploit/failure scenario: `--delete` is added believing it stops the bloat; the `cp -a` keeps growing the disk every deploy, while `--delete` now silently removes any prod-only file under `alembic/versions/` (e.g. a hand-applied hotfix migration) — a new failure mode introduced under a false rationale. Compounded by Step 7 bundling ~7 sub-actions with "decide which during execution, not now" for the three-way systemd port divergence — the exact ambiguous-scope pattern this plan states it exists to avoid.
</details>

**Opus seat returned zero verified findings** — this is the rare, informative signal (cheap seats returning nothing is the observed baseline and not itself noteworthy). Treat as an actual clean bill only after confirming the Opus seat had real repo access and did not time out/error.

## Verdict
Union of all verified findings above, Opus findings weighted highest. This is a report, not a gate — the operator/session is responsible for addressing each finding before implementation.