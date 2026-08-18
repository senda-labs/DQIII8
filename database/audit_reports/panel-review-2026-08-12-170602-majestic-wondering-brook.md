# Panel Review — /root/.claude/plans/majestic-wondering-brook.md

Opus seat spends the operator's own Claude Code session quota (OAuth, no ANTHROPIC_API_KEY configured) — it reuses the existing single-escalation allowance from dqiii8-plan-gate.md, not an additional budget.

**SEAT DEGRADED — epistemic diversity lost:**
- python-specialist: intended nim/deepseek-ai/deepseek-v4-flash, actually served by groq/llama-3.3-70b-versatile
- safety-checker: intended nim/nvidia/llama-3.1-nemoguard-8b-content-safety, actually served by groq/llama-3.3-70b-versatile
Treat NIM seat findings as fewer independent opinions than the seat count implies while this holds.

## python-specialist — API/contract correctness, test coverage
provider=groq model=llama-3.3-70b-versatile status=ok latency_ms=2775
(no verified findings)

<details><summary>4 dropped finding(s) (unverifiable citation — shown, not deleted)</summary>

- [fake_path] [Correctness: considered, issues found]
/root/dqiii8/database/schema_v2.sql:1128-1158
The `trg_agent_actions_close_once` trigger lists `NEW.project IS NOT OLD.project` in its `WHEN` clause, which contradicts the documented design intent. This could lead to incorrect data attribution.
Exploit/failure scenario: Incorrect project attribution due to trigger misconfiguration.
- [fake_path] [Data Integrity: considered, issues found]
/root/dqiii8/.claude/hooks/post_tool_use.py:74-77
The `post_tool_use.py` script imports `db` via `sys.path.insert(bin/)`, but `db.py` lives at `bin/core/db.py`. This could cause a `ModuleNotFoundError` and lead to data inconsistencies.
Exploit/failure scenario: Data inconsistencies due to incorrect import path.
- [no_citation] [Resilience: considered, issues found]
/root/dqiii8/.claude/hooks/session_start.py
The `session_start.py` script uses a dead resolver that always falls through to a literal project name. This could lead to incorrect project attribution and decreased system resilience.
Exploit/failure scenario: Incorrect project attribution due to dead resolver.
- [no_citation] [Operational: considered, issues found]
/root/dqiii8/bin/core/project_context.py
The `project_context.py` script uses a new table `project_context` to store project information. However, the script does not handle cases where the project directory does not exist, which could lead to operational issues.
Exploit/failure scenario: Operational issues due to missing project directory handling.
</details>

## data-specialist — data integrity, blast radius, rollback/undo path
provider=nim model=mistralai/mistral-large-3-675b-instruct-2512 status=error latency_ms=64495
error: [dqiii8.__main__] WARNING circuit open for nim — skipping provider (cooldown 120s)
[dqiii8.__main__] WARNING nim failed — trying next...
[dqiii8.__main__] WARNING groq/llama-3.3-70b-versatile attempt 1/3 failed — retrying in 1.0s
[dqiii8.__main__] WARNING groq/llama-3.3-70b-versatile attempt 2/3 failed — retrying in 2.0s
[dqiii8.__main__] WARNING groq failed — trying next...
[dqiii8.__main__] WARNING openrouter/qwen/qwen3-coder fatal error (auth/config) — not retrying
[dqiii8.__main__] WARNING circuit OPEN for openrouter (8 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING openrouter failed — trying next...
[dqiii8.__main__] WARNING github/deepseek-v3-0324 fatal error (auth/config) — not retrying
[dqiii8.__main__] WARNING circuit OPEN for github (7 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING github failed — trying next...
[dqiii8.__main__] WARNING pollinations/openai attempt 1/3 failed — retrying in 1.0s
[dqiii8.__main__] WARNING pollinations/openai attempt 2/3 failed — retrying in 2.1s
[dqiii8.__main__] WARNING circuit OPEN for pollinations (7 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING pollinations failed — trying next...
[dqiii8.__main__] ERROR all providers failed
(no verified findings)

## safety-checker — destructive-operation and permission review
provider=groq model=llama-3.3-70b-versatile status=ok latency_ms=2670
(no verified findings)

<details><summary>2 dropped finding(s) (unverifiable citation — shown, not deleted)</summary>

- [no_citation] [CATEGORY: Operational] [SEVERITY: P2]
   `/root/dqiii8/database/migrations/2026-08-13_reconcile_open_rows.sql`
   Destructive operation to close and reconcile rows without explicit backup mentioned.
   Exploit/failure scenario: Incorrectly closing or reconciling rows leads to loss of critical data, necessitating a full database restoration from backup.
- [no_citation] [CATEGORY: Operational] [SEVERITY: P3]
   `/root/dqiii8/Context`
   Lack of explicit mention of permission handling in the code.
   Exploit/failure scenario: Insufficient access control potentially leads to unauthorized data modifications or unauthorized access to sensitive information.
</details>

## code-reviewer — adversarial (Opus, single pass)
provider=anthropic model=claude-opus-4-8 status=ok latency_ms=211619
(no verified findings)

<details><summary>5 dropped finding(s) (unverifiable citation — shown, not deleted)</summary>

- [fake_path] I have verified the plan's premises against the actual code. The plan is unusually well-grounded — Corrections A, B, C, D all check out (db.py is at `bin/core/db.py`; `trg_agent_actions_close_once` line 1132 does block `project` backfill; `/root/dqiii8/projects/` is absent while `session_start.py:43` and `user_prompt_submit.py:28` glob it; the DENY branch at `pre_tool_use.py:61-77` exits before the INSERT). Here is what the adversarial pass surfaces that survives verification.
- [fake_path] [CATEGORY: DataIntegrity] [SEVERITY: P1]
/root/dqiii8/.claude/hooks/session_start.py:50 (and post_tool_use.py:248)
The plan mints a **new** canonical name `'dqiii8'` (D1 step 6; project_context validation set `my-projects/* ∪ {dqiii8}`), but the live convention for "the dqiii8 project itself" is `'dqiii8-core'` — hardcoded at `session_start.py:50` and as the `DQIII8_PROJECT` default at `post_tool_use.py:248`. D1's precedence step 2 reads `DQIII8_PROJECT` → yields `'dqiii8-core'`, a value the `/proyecto` validator rejects.
Exploit/failure scenario: self-work rows land under `'dqiii8-core'` (env/wrapper path) while `/proyecto` declarations land under `'dqiii8'`. `v_project_cost_weekly` — the headline deliverable — then splits dqiii8's own hours/cost across two project keys, silently under-reporting each. This is exactly the "datos sin finalidad" the user asked to eliminate, reintroduced by the rebuild.
- [fake_path] [CATEGORY: Correctness] [SEVERITY: P2]
/root/dqiii8/.claude/hooks/pre_tool_use.py:36 (vs subagent_start.py:74)
Stage 1 says "fix the lookup path to match what `subagent_start.py` actually writes," but the mismatch is two-dimensional, not just the directory. `subagent_start.py:74` writes `{DQIII8_ROOT}/tmp/dqiii8_agent_{agent_id}.json` keyed by **agent_id**; the hooks read `/tmp/dqiii8_agent_{session}.json` keyed by **session_id**. Fixing only `/tmp`→`{DQIII8_ROOT}/tmp` still fails because the filename token differs (agent_id ≠ session_id), and the hooks have no agent_id when the file is their only fallback.
Failure scenario: after Stage 1, agent-name resolution for subagent tool calls still misses the file, falls through to `"claude-sonnet-4-6"`, and `v_agent_efficiency` (per-agent attribution — the "detectar optimizaciones" view) keeps collapsing distinct agents into the default name.
- [fake_path] [CATEGORY: Resilience] [SEVERITY: P2]
/root/dqiii8/.claude/hooks/post_tool_use.py:122
The revived close-out (Stage 0) matches the open row by `session_id=? AND tool_used=? AND end_time_ms IS NULL ORDER BY id DESC LIMIT 1` — LIFO. When Claude issues parallel same-tool calls in one turn (common: several Bash/Read at once), each PostToolUse closes the *newest* open row, not its own, cross-attributing `duration_ms`/`success`/`error_message`.
Failure scenario: 3 concurrent Bash calls (fast-fail, slow-ok, medium) close in completion order against id-DESC rows → durations and success flags are shuffled between invocations. Stage 0's stated verification ("live smoke of ~5 tool calls") is sequential and cannot detect this; every downstream cost/success metric inherits the skew.
- [fake_path] [CATEGORY: Operational] [SEVERITY: P2]
/root/dqiii8/bin/core/openrouter_wrapper.py:649 (TIER_COSTS at :293)
Correction E frames Claude Code transcript tokens as "≈99% of real spend" and Stage 5 prices them per-model to USD. But this VPS runs Claude via **OAuth/Claude Max** (`openrouter_wrapper.py:649` delegates to the CLI precisely when no `ANTHROPIC_API_KEY` is set), a flat-rate subscription where marginal per-token cost is $0 until usage caps.
Failure scenario: Stage 5 multiplies `cache_read_input_tokens` (the dominant volume) by list-price rates and writes six-figure-token "cost" into `token_usage`; `v_project_cost_weekly` then reports notional API list-price, not money spent. The plan replaces a cost figure that's "off by orders of magnitude" too low with one that is orders of magnitude too high — and never flags list-price ≠ subscription cost. This distinction must be explicit before Stage 5 is promoted (Open Decision 6).
</details>

**Opus seat returned zero verified findings** — this is the rare, informative signal (cheap seats returning nothing is the observed baseline and not itself noteworthy). Treat as an actual clean bill only after confirming the Opus seat had real repo access and did not time out/error.

## Verdict
Union of all verified findings above, Opus findings weighted highest. This is a report, not a gate — the operator/session is responsible for addressing each finding before implementation.