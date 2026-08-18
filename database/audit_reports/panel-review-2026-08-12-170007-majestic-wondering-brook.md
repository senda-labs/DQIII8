# Panel Review — /root/.claude/plans/majestic-wondering-brook.md

Opus seat spends the operator's own Claude Code session quota (OAuth, no ANTHROPIC_API_KEY configured) — it reuses the existing single-escalation allowance from dqiii8-plan-gate.md, not an additional budget.

**SEAT DEGRADED — epistemic diversity lost:**
- python-specialist: intended nim/deepseek-ai/deepseek-v4-flash, actually served by groq/llama-3.3-70b-versatile
- safety-checker: intended nim/nvidia/llama-3.1-nemoguard-8b-content-safety, actually served by groq/llama-3.3-70b-versatile
Treat NIM seat findings as fewer independent opinions than the seat count implies while this holds.

## python-specialist — API/contract correctness, test coverage
provider=groq model=llama-3.3-70b-versatile status=ok latency_ms=4253
(no verified findings)

<details><summary>2 dropped finding(s) (unverifiable citation — shown, not deleted)</summary>

- [no_citation] [Correctness: Data Integrity]
database/schema_v2.sql
Introduction of `project_context` table and amendments to existing triggers aim to improve data integrity and attribution correctness.
Exploit/failure scenario: Incorrect data attribution could lead to incorrect cost and project tracking, affecting project management and optimization efforts.
- [no_citation] However, the primary critique and findings are more about the approach and potential implications rather than specific, exploitable issues in the code. The plan appears to be a comprehensive effort to address data integrity, attribution, and correctness, with a focus on enhancing the system's capability to accurately track project-related data and costs.
</details>

## data-specialist — data integrity, blast radius, rollback/undo path
provider=nim model=mistralai/mistral-large-3-675b-instruct-2512 status=error latency_ms=64690
error: [dqiii8.__main__] WARNING circuit open for nim — skipping provider (cooldown 120s)
[dqiii8.__main__] WARNING nim failed — trying next...
[dqiii8.__main__] WARNING groq/llama-3.3-70b-versatile attempt 1/3 failed — retrying in 1.0s
[dqiii8.__main__] WARNING groq/llama-3.3-70b-versatile attempt 2/3 failed — retrying in 2.1s
[dqiii8.__main__] WARNING groq failed — trying next...
[dqiii8.__main__] WARNING openrouter/qwen/qwen3-coder fatal error (auth/config) — not retrying
[dqiii8.__main__] WARNING circuit OPEN for openrouter (7 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING openrouter failed — trying next...
[dqiii8.__main__] WARNING github/deepseek-v3-0324 fatal error (auth/config) — not retrying
[dqiii8.__main__] WARNING circuit OPEN for github (6 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING github failed — trying next...
[dqiii8.__main__] WARNING pollinations/openai attempt 1/3 failed — retrying in 1.2s
[dqiii8.__main__] WARNING pollinations/openai attempt 2/3 failed — retrying in 2.2s
[dqiii8.__main__] WARNING circuit OPEN for pollinations (6 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING pollinations failed — trying next...
[dqiii8.__main__] ERROR all providers failed
(no verified findings)

## safety-checker — destructive-operation and permission review
provider=groq model=llama-3.3-70b-versatile status=ok latency_ms=2426
(no verified findings)

<details><summary>6 dropped finding(s) (unverifiable citation — shown, not deleted)</summary>

- [fake_path] [CATEGORY: Operational] [SEVERITY: P2]
/root/dqiii8/.claude/hooks/post_tool_use.py:74-77
The post_tool_use.py script has a potential issue with its import statement, which could lead to a ModuleNotFoundError if the path to the db module is not correctly configured.
- [fake_path] [CATEGORY: Security] [SEVERITY: P2]
/root/dqiii8/database/schema_v2.sql:1128-1158
The trg_agent_actions_close_once trigger has a potential issue with its WHEN clause, which could lead to incorrect data being written to the database.
- [fake_path] [CATEGORY: DataIntegrity] [SEVERITY: P2]
/root/dqiii8/.claude/hooks/pre_tool_use.py:36
The pre_tool_use.py script has a potential issue with its agent-name resolution, which could lead to incorrect data being written to the database.
- [no_citation] [CATEGORY: Correctness] [SEVERITY: P3]
/root/dqiii8/bin/ui/dqiii8_bot.py
The dqiii8_bot.py script has a potential issue with its character count logging, which could lead to incorrect data being written to the database.
- [no_citation] [CATEGORY: Resilience] [SEVERITY: P3]
/root/dqiii8/database/migrations/2026-08-13_agent_actions_request_id.{up,down}.sql
The 2026-08-13_agent_actions_request_id migration has a potential issue with its trigger amendment, which could lead to incorrect data being written to the database.
- [no_citation] Exploit/failure scenario for each of the issues:
1. An attacker could potentially exploit the ModuleNotFoundError issue in post_tool_use.py by manipulating the path to the db module, leading to a denial-of-service attack.
2. An attacker could potentially exploit the trg_agent_actions_close_once trigger issue by manipulating the data being written to the database, leading to incorrect data being stored.
3. An attacker could potentially exploit the agent-name resolution issue in pre_tool_use.py by manipulating the agent names, leading to incorrect data being written to the database.
4. An attacker could potentially exploit the character count logging issue in dqiii8_bot.py by manipulating the character counts, leading to incorrect data being written to the database.
5. An attacker could potentially exploit the trigger amendment issue in the 2026-08-13_agent_actions_request_id migration by manipulating the data being written to the database, leading to incorrect data being stored.
</details>

## code-reviewer — adversarial (Opus, single pass)
provider=anthropic model=claude-opus-4-8 status=ok latency_ms=195554
(no verified findings)

<details><summary>6 dropped finding(s) (unverifiable citation — shown, not deleted)</summary>

- [fake_path] I've grounded the plan's load-bearing claims against the actual code. Corrections A (post_tool_use.py:75–78 inserts `bin/` but `db.py` is at `bin/core/db.py` → real `ModuleNotFoundError`) and B (the `NEW.project IS NOT OLD.project` guard at schema_v2.sql:1132 does block project backfill) both check out. Here is the adversarial verdict by category.
- [fake_path] **Security: considered, one disclosed residual, no new finding.** The NL project matcher (D2.3) lets arbitrary prompt text silently re-attribute all downstream cost/hours to another project until `/proyecto fin`. This is a real tampering/attribution-integrity vector, but the plan surfaces it explicitly (Open Decision 3, high-precision matcher, one-shot echo-back). Fail-closed posture of the write path (pre_tool_use.py:52) is preserved. No new security regression introduced.
- [fake_path] [CATEGORY: Resilience] [SEVERITY: P2]
schema_v2.sql:1127 (`WHEN OLD.end_time_ms IS NOT NULL`) — via the Stage 0/Stage 1 split
The plan mandates Stage 0 land **alone** ("Must land and be verified alone"), but the `sqlite3.IntegrityError` catch for the now-live double-close is deferred to Stage 1.
Exploit/failure scenario: Once Stage 0 revives post_tool_use's close-out, both post_tool_use and post_tool_use_failure attempt the single permitted close. The second UPDATE hits `OLD.end_time_ms IS NOT NULL` → `RAISE(ABORT)`. Between the Stage-0-alone deploy and Stage 1, every failed tool call raises an uncaught IntegrityError in the failure hook (skipping its error_log INSERT), for the first time in two months — a regression window the staging itself creates. Fold the IntegrityError catch into Stage 0.
- [fake_path] [CATEGORY: Correctness] [SEVERITY: P2]
post_tool_use.py:122 (`WHERE session_id=? AND tool_used=? AND end_time_ms IS NULL ORDER BY id DESC LIMIT 1`)
Close-out matches by (session, tool) + LIFO, not by the pre_tool_use row's `id`. Stage 0 revives this at 100% volume, and Stage 4's `v_project_cost_weekly`/`v_agent_efficiency` derive hours/cost from the resulting `duration_ms`.
Exploit/failure scenario: Two concurrent same-tool calls in one turn (rules explicitly cite "parallel dispatch") → PostToolUse for the first-completing call closes the *newest* open row, swapping durations/success between the two invocations. Aggregate per-project totals mostly survive, but per-action duration/success (the "detectar optimizaciones" signal) is mis-attributed. The plan asserts close-out simply "works" once the path is fixed; the matching key is unsound and unaddressed.
- [fake_path] [CATEGORY: DataIntegrity] [SEVERITY: P2]
pre_tool_use.py:108–110 (INSERT column list omits `request_id`)
Stage 3 adds `request_id` to the immutability trigger, but the hook write path never populates it, and the trigger then makes it permanently NULL.
Exploit/failure scenario: Only wrapper `api_call` rows get a `request_id`; the far larger population of hook tool-call rows insert it as NULL and can never be backfilled (immutable). `v_agent_efficiency`'s "request-level success rate" therefore silently covers only cascade wrapper calls — defensible as the intended scope, but the plan doesn't state this coverage limit, so the "3.8% real failure rate becomes queryable" claim reads broader than it is.
- [fake_path] [CATEGORY: Operational] [SEVERITY: P2]
pre_tool_use.py:106 (`sqlite3.connect(_DB, timeout=10)`)
Stage 2 wires `resolve_project()` — a `project_context` SELECT — into this hot path, which runs on **every** tool call.
Exploit/failure scenario: The injected rules already warn that the 10s hook timeout produces `SQLITE_BUSY` under parallel dispatch. Adding a second query per tool call to the pre-insert critical section increases lock-hold time and contention; on `SQLITE_BUSY` the broad `except` (line 117) silently drops the row — reintroducing exactly the open/missing-row loss Stage 0 exists to fix. Resolve project without a per-call synchronous read (cache the open global row, or pass via env).
</details>

**Opus seat returned zero verified findings** — this is the rare, informative signal (cheap seats returning nothing is the observed baseline and not itself noteworthy). Treat as an actual clean bill only after confirming the Opus seat had real repo access and did not time out/error.

## Verdict
Union of all verified findings above, Opus findings weighted highest. This is a report, not a gate — the operator/session is responsible for addressing each finding before implementation.