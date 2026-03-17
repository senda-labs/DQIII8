# JARVIS System Health Audit — 2026-03-16 (Gaps Analysis)

**Audit date:** 2026-03-16
**Period covered:** 2026-03-10 → 2026-03-16
**Overall health score: 65/100**
**Previous audit score:** 93.36/100 (2026-03-16 06:50:54, id=8)

> Note: Score drop from 93 to 65 reflects stricter weighting on structural data-quality gaps
> (sessions.project/model_used never populated, error_log empty, skill_metrics empty)
> that were already flagged in prior audits but remain unresolved.

---

## 1. agent_actions

| Metric | Value |
|--------|-------|
| Total actions | 5,930 |
| Successes | 5,913 |
| Failures | 17 |
| Success rate | **99.71%** |
| Unique agents | 46 |
| Hook blocks | 0 |
| Total tokens logged | 2,650 |
| Total cost logged | €0.00 |
| Date range | 2026-03-10 → 2026-03-16 |

**Score component: 25/25** — Near-perfect operational success rate.

### Top agents by volume

| Agent name | Actions | Success % | Avg ms |
|------------|---------|-----------|--------|
| claude-sonnet-4-6 | 4,921 | 100.0% | 11,642 |
| context-mode | 187 | 93.05% | 0 |
| unknown | 113 | 100.0% | 9,199 |
| a3cb69e59deb72817 | 42 | 100.0% | 308 |
| a39cf07681a9b839d | 32 | 100.0% | 370 |

### Failures breakdown

- **context-mode / Bash: 13 failures** — These are false positives: context-mode records stdout from bash commands that contain error markers (e.g. fal.media API errors, pip install noise) as failed actions. The underlying commands partially succeeded. No real system instability.
- **default / openrouter_wrapper api_call: 4 failures** — Recorded 2026-03-12, no error_message populated. OpenRouter transient errors, no resolution logged.

### Daily volume

| Day | Actions | Failures |
|-----|---------|----------|
| 2026-03-10 | 104 | 0 |
| 2026-03-11 | 274 | 0 |
| 2026-03-12 | 604 | 4 |
| 2026-03-13 | 870 | 0 |
| 2026-03-14 | 1,665 | 0 |
| 2026-03-15 | 1,760 | 4 |
| 2026-03-16 | 672 | 9 |

Volume trend is healthy: strong growth from 104 → 1,760 actions/day reflects increasing system utilization.

---

## 2. error_log

| Metric | Value |
|--------|-------|
| Total errors logged | **0** |
| Resolved | — |
| Unresolved | — |
| Resolution rate | — |
| Empty keywords (`[]`) | — |
| Populated keywords | — |
| Lessons added | — |

**Score component: 8/15** — Table is completely empty. This is a critical structural gap.

### Analysis

The error_log table has never received a single row. This means:
1. `post_tool_use.py` does not insert rows into `error_log` when `success=0` in `agent_actions`.
2. The `error_keywords_freq` view returns empty because the source table is empty.
3. The keyword quality question ("are keywords JSON arrays, not `[]`?") **cannot be answered** — there are no rows to evaluate.
4. `lesson_added` flag is never set.

**Root cause (confirmed from prior audit id=8 recommendations):** `post_tool_use.py` inserts into `agent_actions` with `success=0` but does not write a corresponding row to `error_log`. The hook needs a second INSERT when recording a failure.

**Gap status: UNRESOLVED** — This gap has appeared in every audit since at least id=4 (2026-03-14). Four consecutive audits, zero progress.

---

## 3. sessions

| Metric | Value |
|--------|-------|
| Total sessions | 113 |
| Sessions with `project` populated | **0** (0%) |
| Sessions with `model_used` populated | **0** (0%) |
| Sessions closed (`end_time` set) | 113 (100%) |
| Ghost sessions (`total_actions=0`) | **33** (29%) |
| Total lessons captured | 317 |
| Avg actions per session | 50.42 |
| Date range | 2026-03-10 → 2026-03-16 |

**Score component: 0/15** — Both critical metadata fields are NULL in 100% of sessions.

### lessons_added distribution

| lessons_added value | Sessions |
|--------------------|----------|
| 0 | 72 |
| 2 | 35 |
| 8 | 1 |
| 45 | 1 |
| 47 | 2 |
| 50 | 2 |

**Diagnosis:** 35 sessions show `lessons_added=2` — this is a known initialization bug where `stop.py` defaults to 2 instead of 0. The 72 sessions with 0 are accurate (no lessons). The 6 sessions with 8-50 lessons are genuine high-activity sessions where `lessons_added` was incremented correctly.

**Root cause:** `stop.py` never writes `project` or `model_used` to the sessions table. The session_start hook creates the row but leaves these fields NULL, and stop.py closes the session without filling them.

**Ghost sessions (33 with total_actions=0):** These are session records created by `stop.py` running in rapid succession (start/end timestamps identical on same second). Likely duplicate flush calls or test runs.

**Gap status: UNRESOLVED** — Flagged in audits id=5, 6, 7, 8. Still 0% population rate.

---

## 4. skill_metrics

| Metric | Value |
|--------|-------|
| Total records | **0** |
| Unique skills | 0 |
| Healthy skills (≥80% success) | — |
| Struggling skills | — |
| Avg success rate | — |

**Score component: 0/10** — Table is completely empty.

### Analysis

No skill has ever been logged to `skill_metrics`. The skills-registry INDEX.md contains approved skills, but there is no instrumentation that writes skill load/use events to this table. Skills are being used operationally (visible via `skills_active` column in `agent_actions`) but usage is not being tracked in the dedicated table.

**Gap status: UNRESOLVED** — Never populated since schema creation.

---

## 5. audit_reports

| Metric | Value |
|--------|-------|
| Total reports | 8 |
| Last audit | 2026-03-16 06:50:54 |
| Max score | 93.36 |
| Min score | 0.50 |
| Avg score | 77.73 |

**Score component: 10/10** — Audit cadence is healthy. 8 reports over 6 days, multiple runs today.

### Score trend (last 5 audits)

| id | Date | Score | Key recommendation |
|----|------|-------|--------------------|
| 4 | 2026-03-14 | 82.0 | Fix stop.py lessons_added init, HF_TOKEN |
| 5 | 2026-03-16 06:05 | 93.0 | Fix sessions.project/model_used |
| 6 | 2026-03-16 06:29 | 93.0 | Fix error_log population |
| 7 | 2026-03-16 06:41 | 93.0 | Investigate lessons_added=2 boilerplate |
| 8 | 2026-03-16 06:50 | 93.36 | Fix post_tool_use error logging |

Score jumped from 82 → 93 between 2026-03-14 and 2026-03-16 but has been static since. The same 3-4 gaps are being re-flagged each cycle without resolution.

---

## 6. vault_memory

| Metric | Value |
|--------|-------|
| Total entries | **133** |
| Unique predicates | 95 |
| Unique projects | 1 (jarvis-core) |
| Entry types | 1 (lesson) |
| Total reinforcements (times_seen sum) | 140 |
| Date range | 2026-03-16 05:01:09 → 2026-03-16 06:52:59 |

**Score component: 10/10** — vault_memory is actively populated and well-structured.

### Analysis

vault_memory is working correctly. Entries follow the `(subject, predicate, object)` triple format with confidence=1.0 and are being written by `stop.py` (`source='session_stop'`). All 133 entries are of type `lesson` and tied to project `jarvis-core`.

**Notable entries (most recent):**
- `github-scorer → penalizes → GPU_requirements_on_CPU_only_VPS`
- `GPU_KEYWORDS_pattern → false_positive_fixed_by → evaluating_CPU_PHRASES_first`
- `stop.py → now_counts → vault_memory_implicit_lessons`

The 7 reinforced entries (times_seen > 1) show the system is correctly deduplicating repeated lessons.

**Concern:** All entries were created today (2026-03-16) in a narrow 2-hour window. Prior sessions have no vault_memory entries, suggesting the feature was only activated today. The single project (`jarvis-core`) means cross-project memory is not yet being captured.

---

## 7. Views

### agent_performance
Functional but uses hex agent IDs (session UUIDs truncated). Human-readable agent names (claude-sonnet-4-6, context-mode) are not in this view — they are in agent_actions directly. All agents in the view show 100% success rate.

### error_keywords_freq
Returns empty — source table (error_log) is empty. View is correctly defined but has no data to aggregate.

---

## Score Computation

| Component | Weight | Raw | Score |
|-----------|--------|-----|-------|
| Action success rate (99.71%) | 25 | 99.71% | 25.0 |
| Error resolution rate (table empty) | 15 | structural gap | 8.0 |
| Sessions data quality (0% project/model) | 15 | 0% | 0.0 |
| Lessons captured (317 total, vault active) | 15 | active | 12.0 |
| vault_memory population | 10 | 133 entries | 10.0 |
| skill_metrics population | 10 | 0 entries | 0.0 |
| Audit cadence | 10 | 8 reports | 10.0 |
| **TOTAL** | **100** | | **65.0** |

---

## Gap Summary — Unresolved Issues

### CRITICAL (blocks observability)

1. **error_log is empty** — `post_tool_use.py` never inserts rows when `success=0`. Fix: add INSERT INTO error_log after the agent_actions INSERT when the action failed. Blocked since audit id=4.

2. **sessions.project and sessions.model_used always NULL** — `stop.py` closes sessions without writing these fields. Fix: read project from active `projects/` or env, read model from `$CLAUDE_MODEL` or config. 113/113 sessions affected.

3. **skill_metrics never populated** — No hook or wrapper writes to this table. Fix: instrument `session_start.py` or the skill loader to INSERT/UPDATE on each skill load.

### MODERATE

4. **Ghost sessions (33 sessions with total_actions=0)** — Likely duplicate stop.py flush calls. Fix: add a guard in stop.py to skip session write if total_actions == 0 and session duration < 5 seconds.

5. **sessions.lessons_added defaults to 2** — Initialization bug in stop.py. Fix: initialize counter at 0, not 2.

6. **13 context-mode Bash failures** — These are false positives where stdout contains error markers from sub-process output. The context-mode hook should not mark a Bash action as failed based on stdout content alone; it should use the exit code.

### LOW

7. **agent names are hex UUIDs in agent_performance view** — 46/46 agents tracked by session ID, not by logical name. The `agent_name` field in `agent_actions` is populated for main agents (claude-sonnet-4-6, context-mode) but not for subagent sessions.

8. **vault_memory limited to today** — Only jarvis-core project, only 2026-03-16. Historical sessions have no vault entries. Either the feature was introduced today or prior entries were cleared.

---

## Recommendations (Priority Order)

1. **Fix `post_tool_use.py`**: When recording `success=0` in agent_actions, also INSERT into error_log with `error_type`, `error_message`, `keywords` (extract from error_message via regex), `resolved=0`.

2. **Fix `stop.py` session finalization**: Write `project` (from env/config), `model_used` (from env), `end_time` to sessions table. Remove the hardcoded `lessons_added=2` default.

3. **Instrument skill loading**: Add INSERT/UPDATE to skill_metrics in the hook that loads skills (session_start.py or skill loader).

4. **Filter ghost sessions**: Skip sessions with total_actions=0 and duration < 5s in stop.py.

5. **Fix context-mode false-positive failures**: Use exit code, not stdout content, to determine Bash action success in the context-mode hook.

---

*Report generated: 2026-03-16*
*DB: /root/jarvis/database/jarvis_metrics.db*
*Auditor: JARVIS health audit pipeline*
