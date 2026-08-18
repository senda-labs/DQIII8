# Panel Review — /root/.claude/plans/distributed-wobbling-gem.md

Opus seat spends the operator's own Claude Code session quota (OAuth, no ANTHROPIC_API_KEY configured) — it reuses the existing single-escalation allowance from dqiii8-plan-gate.md, not an additional budget.

**SEAT DEGRADED — epistemic diversity lost:**
- python-specialist: intended nim/deepseek-ai/deepseek-v4-flash, actually served by groq/llama-3.3-70b-versatile
- safety-checker: intended nim/nvidia/llama-3.1-nemoguard-8b-content-safety, actually served by groq/llama-3.3-70b-versatile
Treat NIM seat findings as fewer independent opinions than the seat count implies while this holds.

## python-specialist — API/contract correctness, test coverage
provider=groq model=llama-3.3-70b-versatile status=ok latency_ms=3821
(no verified findings)

## data-specialist — data integrity, blast radius, rollback/undo path
provider=nim model=mistralai/mistral-large-3-675b-instruct-2512 status=error latency_ms=65173
error: [dqiii8.__main__] WARNING circuit open for nim — skipping provider (cooldown 120s)
[dqiii8.__main__] WARNING nim failed — trying next...
[dqiii8.__main__] WARNING groq/llama-3.3-70b-versatile attempt 1/3 failed — retrying in 1.1s
[dqiii8.__main__] WARNING groq/llama-3.3-70b-versatile attempt 2/3 failed — retrying in 2.2s
[dqiii8.__main__] WARNING groq failed — trying next...
[dqiii8.__main__] WARNING openrouter/qwen/qwen3-coder fatal error (auth/config) — not retrying
[dqiii8.__main__] WARNING circuit OPEN for openrouter (10 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING openrouter failed — trying next...
[dqiii8.__main__] WARNING github/deepseek-v3-0324 fatal error (auth/config) — not retrying
[dqiii8.__main__] WARNING circuit OPEN for github (9 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING github failed — trying next...
[dqiii8.__main__] WARNING pollinations/openai attempt 1/3 failed — retrying in 1.0s
[dqiii8.__main__] WARNING pollinations/openai attempt 2/3 failed — retrying in 2.2s
[dqiii8.__main__] WARNING circuit OPEN for pollinations (9 consecutive failures, cooldown 120s)
[dqiii8.__main__] WARNING pollinations failed — trying next...
[dqiii8.__main__] ERROR all providers failed
(no verified findings)

## safety-checker — destructive-operation and permission review
provider=groq model=llama-3.3-70b-versatile status=ok latency_ms=2533

- [P2] [Operational: destructive ops and permission scope] [SEVERITY: P2]
database/migrations/2026-08-13_project_value_and_budget.up.sql:1 
Destructive operation - dropping and recreating tables can lead to data loss if not done properly, however, it's mitigated by using a scratch DB copy first.
Exploit/failure scenario: Applying the migration to the live database directly without testing on a scratch copy can cause data loss.
- [P2] [Operational: destructive ops and permission scope] [SEVERITY: P2]
database/migrations/2026-08-13_project_context_status.up.sql:1 
Destructive operation - altering the project_context table can lead to data inconsistencies if not done correctly, however, it's mitigated by using a scratch DB copy first.
Exploit/failure scenario: Applying the migration to the live database directly without testing on a scratch copy can cause data inconsistencies.
- [P2] [Operational: destructive ops and permission scope] [SEVERITY: P2]
database/migrations/2026-08-13_roi_views.up.sql:1 
Destructive operation - dropping and recreating views can lead to data inconsistencies if not done properly, however, it's mitigated by using a scratch DB copy first.
Exploit/failure scenario: Applying the migration to the live database directly without testing on a scratch copy can cause data inconsistencies.
- [P3] [Operational: cost/quota] [SEVERITY: P3]
bin/core/project_context.py:1 
Adding new tables, columns, and views can increase storage costs, however, the impact seems minimal.
Exploit/failure scenario: The increased storage costs can lead to unexpected expenses if not monitored properly.

## code-reviewer — adversarial (Opus, single pass)
provider=anthropic model=claude-opus-4-8 status=ok latency_ms=182227

- [Correctness] [P1] [CATEGORY: Correctness] [SEVERITY: P1]
database/schema_v2.sql:1050-1054 (consumed by v_project_roi:1094, v_budget_deviation:1134)
`v_project_cost_weekly` is built `FROM agent_agg LEFT JOIN human_agg`, so any `(project, iso_week)` with logged human hours but **zero agent_actions that week is dropped entirely**. ROI/budget then `SUM(human_hours)` off this view.
Exploit/failure scenario: You work a project manually for a week (log `human_hours`) with no agent runs. Those hours never reach `v_project_roi.coste_humano_eur` → labour cost understated → `roi_eur` overstated and `desviacion_pct` understated. The two headline economic numbers are silently biased upward.
- [Correctness] [P2] [CATEGORY: Correctness] [SEVERITY: P2]
bin/core/project_context.py:210-213
`set_project_status` does `UPDATE ... WHERE project=? AND ended_at IS NULL`. Projects are marked `'entregado'`/`'abandonado'` precisely when finished — but a finished project's `project_context` rows are already closed (`end_project` sets `ended_at`), so there is **no open row to update**.
Exploit/failure scenario: `project_ctl.py status nl-onion entregado` on a delivered project updates 0 rows, commits, returns success. The user believes status was set; `get_project_status` returns `None`. Terminal statuses are unsettable for exactly the projects they describe.
- [DataIntegrity] [P2] [CATEGORY: DataIntegrity] [SEVERITY: P2]
database/schema_v2.sql:1097-1099, 1110 (with v_infra_cost_weekly:1064-1082)
`v_infra_cost_weekly` applies the *current* monthly pool to *every* historical week; `v_project_roi`/`v_budget_deviation` then `SUM(infra_cost_eur)` across all weeks. Total infra charged ≈ `monthly_pool/4.345 × (#weeks the project appears)`, unbounded in project lifetime.
Exploit/failure scenario: A project active 30 weeks accrues ~30 weekly-pool shares of VPS/subscription cost that mostly never existed for it. The "Known limitations" note frames this as cosmetic ("early weeks"), but it materially inflates `coste_infra_eur` and depresses `roi_eur` proportional to age — under-disclosed.
- [DataIntegrity] [P2] [CATEGORY: DataIntegrity] [SEVERITY: P2]
database/schema_v2.sql:1114
`v_project_roi` is `FROM value_agg` (project_value) LEFT JOIN costs. A project with costs but **no `project_value` row never appears at all**, so its human+infra cost is invisible to any ROI aggregate.
Exploit/failure scenario: An internal-automation project with real hours but no logged fee shows nowhere in ROI; its allocated infra share silently drops from the books. Loss-making unbilled work is structurally hidden.

<details><summary>5 dropped finding(s) (unverifiable citation — shown, not deleted)</summary>

- [fake_path] I have verified the plan against the actual repo — the views (`schema_v2.sql:1064-1172`) and functions (`project_context.py:181-312`) are already implemented, so I can cite real lines. Adversarial findings by category:
- [fake_path] **Security: considered, no issues found.** All writes use parameterized queries (`project_context.py:192-195, 262-265`); free-text `nota`/`basis` are bound params, not interpolated. Single-user VPS, no privilege boundary crossed.
- [fake_path] [CATEGORY: Resilience] [SEVERITY: P2]
Plan §Files → `2026-08-13_project_value_and_budget.down.sql` (drops labor_rates/infra_costs/project_value/project_budget)
The 5 views (`schema_v2.sql:1087-1172`) reference these tables, but the plan specifies no down-migration ordering. Rolling back the tables while the views persist orphans them.
Exploit/failure scenario: Rollback runs the tables `.down` without first dropping views → `SELECT * FROM v_project_roi` errors "no such table: project_value", breaking every consumer (`get_project_roi`, bot status branch). Secondary: if `labor_rates` is emptied, the views' scalar `(SELECT rate_eur_hour FROM rate)` returns NULL → `roi_eur` becomes NULL silently rather than erroring (`get_labor_rate` masks it further by returning `0.0`, `project_context.py:278`).
- [fake_path] **Operational: considered, minor only.** Scratch-DB-first sequencing and CHECK constraints are sound. Note P3 drift: the plan cites `majestic-wondering-brook.md:489-556` as SSOT but the shipped schema comment cites `distributed-wobbling-gem.md` (`schema_v2.sql:1059`); and `status` is write-only — no view consumes it, so it adds no analytic value yet.
- [fake_path] **Verdict: CHANGES REQUIRED** — Critical: 1 (P1 human-hours drop) · Serious: 4. Top issue: labour cost silently understated → ROI overstated → `schema_v2.sql:1050`.
</details>

## Verdict
Union of all verified findings above, Opus findings weighted highest. This is a report, not a gate — the operator/session is responsible for addressing each finding before implementation.