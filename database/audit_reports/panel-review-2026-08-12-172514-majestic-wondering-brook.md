# Panel Review — /root/.claude/plans/majestic-wondering-brook.md

Opus seat spends the operator's own Claude Code session quota (OAuth, no ANTHROPIC_API_KEY configured) — it reuses the existing single-escalation allowance from dqiii8-plan-gate.md, not an additional budget.

**SEAT DEGRADED — epistemic diversity lost:**
- python-specialist: intended nim/deepseek-ai/deepseek-v4-flash, actually served by groq/llama-3.3-70b-versatile
- safety-checker: intended nim/nvidia/llama-3.1-nemoguard-8b-content-safety, actually served by groq/llama-3.3-70b-versatile
Treat NIM seat findings as fewer independent opinions than the seat count implies while this holds.

## python-specialist — API/contract correctness, test coverage
provider=groq model=llama-3.3-70b-versatile status=ok latency_ms=4288
(no verified findings)

<details><summary>1 dropped finding(s) (unverifiable citation — shown, not deleted)</summary>

- [fake_path] [CATEGORY: Correctness] [SEVERITY: P2]
./path/to/relevant/file.py:123
The plan does not explicitly discuss how API contracts are validated or how comprehensive the test coverage is for the proposed changes.
</details>

## data-specialist — data integrity, blast radius, rollback/undo path
provider=nim model=mistralai/mistral-large-3-675b-instruct-2512 status=error latency_ms=64707
error: [dqiii8.__main__] WARNING circuit open for nim — skipping provider (cooldown 120s)
[dqiii8.__main__] WARNING nim failed — trying next...
[dqiii8.__main__] WARNING groq/llama-3.3-70b-versatile attempt 1/3 failed — retrying in 1.0s
[dqiii8.__main__] WARNING groq/llama-3.3-70b-versatile attempt 2/3 failed — retrying in 2.2s
[dqiii8.__main__] WARNING groq failed — trying next...
[dqiii8.__main__] WARNING openrouter/qwen/qwen3-coder fatal error (auth/config) — not retrying
[dqiii8.__main__] WARNING circuit OPEN for openrouter (9 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING openrouter failed — trying next...
[dqiii8.__main__] WARNING github/deepseek-v3-0324 fatal error (auth/config) — not retrying
[dqiii8.__main__] WARNING circuit OPEN for github (8 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING github failed — trying next...
[dqiii8.__main__] WARNING pollinations/openai attempt 1/3 failed — retrying in 1.1s
[dqiii8.__main__] WARNING pollinations/openai attempt 2/3 failed — retrying in 2.0s
[dqiii8.__main__] WARNING circuit OPEN for pollinations (8 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING pollinations failed — trying next...
[dqiii8.__main__] ERROR all providers failed
(no verified findings)

## safety-checker — destructive-operation and permission review
provider=groq model=llama-3.3-70b-versatile status=ok latency_ms=2215
(no verified findings)

<details><summary>3 dropped finding(s) (unverifiable citation — shown, not deleted)</summary>

- [no_citation] Resilience: 
[CATEGORY: Resilience] [SEVERITY: P2]
/root/dqiii8/database/migrations/2026-08-13_views_rebuild.{up,down}.sql
The plan does not account for potential timeouts or retry hazards when executing database migrations, which could lead to inconsistencies in the database state.
Exploit/failure scenario: A database migration fails due to a timeout, leaving the database in an inconsistent state, and subsequent queries or updates may produce incorrect results or errors.
- [fake_path] Operational: 
[CATEGORY: Operational] [SEVERITY: P2]
/root/dqiii8/.claude/hooks/post_tool_use.py:74-77
The code has a potential issue with the import path for the 'db' module, which could lead to a ModuleNotFoundError if the path is not correctly configured.
Exploit/failure scenario: The 'db' module is not found due to an incorrect import path, causing a ModuleNotFoundError and potentially disrupting the tool's functionality.
- [no_citation] [CATEGORY: Operational] [SEVERITY: P2]
/root/dqiii8/bin/core/project_context.py
The plan introduces a new table 'project_context' to serve as a single source of truth for the current project, but it does not explicitly handle potential errors or edge cases that may arise during the resolution of the project context.
Exploit/failure scenario: An error occurs during the resolution of the project context, causing the tool to fail or produce incorrect results, potentially leading to inconsistencies in the database or incorrect project attributions.
</details>

## code-reviewer — adversarial (Opus, single pass)
provider=anthropic model=claude-opus-4-8 status=ok latency_ms=145360

- [Correctness] [P1] [CATEGORY: Correctness] [SEVERITY: P1]
`.claude/hooks/post_tool_use.py:248` (against D1 precedence step 2)
D1 ranks the `DQIII8_PROJECT` env var (step 2) *above* the user's live global `project_context` declaration (step 4), but the env var lives in the already-running CC process and cannot be mutated cross-process.
Exploit/failure scenario: CC session boots under project A → Stage 2's `session_start.py` exports `DQIII8_PROJECT=A`. Mid-session the user sends Telegram `/proyecto B` (D2 entry point #1, a *different* process — it writes the DB row but cannot touch the CC process's environment). Every subsequent tool call resolves via step 2 → still `A`; `post_tool_use.py:248`'s `os.environ.get("DQIII8_PROJECT","dqiii8-core")` also reads stale `A`. All rows misattribute to A — the exact "datos sin finalidad" cross-key split the rebuild exists to kill. The plan's mitigation ("refresh env on `/proyecto` call") only fires for in-process CLI/prompt calls, never the Telegram path it names as primary.
- [DataIntegrity] [P2] [CATEGORY: DataIntegrity] [SEVERITY: P2]
`.claude/hooks/pre_tool_use.py:112`
Stage 0's fallback close-out key `(session_id, tool_used, file_path, start_time_ms)` cannot match, because the INSERT truncates `file_path` to 120 chars (`[:120]`) while `post_tool_use.py:53/66` reads the untruncated value.
Exploit/failure scenario: any Edit/Write on a path longer than 120 chars (common with nested `my-projects/<x>/...` trees) inserts a truncated `file_path`, so the `tool_use_id`-absent fallback compares full-vs-truncated, finds no row, and creates a fresh orphan — silently regenerating the very open-row population Stage 0 is deployed to eliminate, and passing the sequential smoke test because short scratch paths match fine.
- [Resilience] [P1] [CATEGORY: Resilience] [SEVERITY: P1]
`.claude/hooks/post_tool_use.py:118` (and `pre_tool_use.py:106`)
Stage 0 rewrites the close-out *matching key* but never raises the sub-30s SQLite timeouts (`_get_db(timeout=2)` on close-out; `timeout=10` on the INSERT), which this repo's own rules state cause `SQLITE_BUSY` loss under parallel dispatch.
Exploit/failure scenario: Correction H's own parallel smoke test (several concurrent same-tool calls) is exactly the load that trips `timeout=2`; on the VPS a busy turn drops the close-out UPDATE, the broad `except Exception` at `post_tool_use.py:203` swallows it, and the row stays open. Stage 0 declares victory (import fixed, key fixed) while the orphan rate silently persists from a second, unaddressed root cause. The parallel test may pass by timing luck on an idle scratch DB and mask it.
- [Operational] [P2] [CATEGORY: Operational] [SEVERITY: P2]
Stage 6 B1 assertion + D7 vs Stage 7 claim (`database/schema_v2.sql:1132`, trigger `WHEN NEW.project IS NOT OLD.project`)
Two coupled operational defects. (1) B1's `assert changes()=1332 exactly` treats a *today-snapshot* count as invariant, but Stages 0→1→2→5→3→4 execute first — any wrapper rows left `end_time_ms IS NULL` during that window shift the count and abort the whole reconciliation. (2) Correction D7 admits `request_id` is "never backfillable" once added to the immutable `WHEN` list, yet Stage 7 claims `v_agent_efficiency`'s request-level rate "covers the whole table, not just wrapper calls" — false for all 3,644 historical rows (permanent NULL `request_id`), so the "no coverage-limitation caveat" instruction to Stage 7 docs is itself the caveat that must not be dropped.

<details><summary>1 dropped finding(s) (unverifiable citation — shown, not deleted)</summary>

- [fake_path] **Verdict: CHANGES REQUIRED.** The plan's grounding corrections (A–H) are genuinely well-verified against real code — I confirmed the `db`-import path break, the `agent_id`/`session_id` two-dimensional lookup mismatch (`subagent_start.py:74` vs `pre_tool_use.py:36`), the `project` immutability trigger (`schema_v2.sql:1132`), and the LIFO close-out. The defects above are second-order: the plan fixes the failures it *named* but leaves adjacent mechanisms (timeout, path truncation, env-var precedence, snapshot asserts) that re-open the same wounds. Critical: 0 auth/data-loss. P1: 2. P0 not present. Address the P1 precedence and timeout gaps before Stage 0 lands.
</details>

## Verdict
Union of all verified findings above, Opus findings weighted highest. This is a report, not a gate — the operator/session is responsible for addressing each finding before implementation.