---
name: auditor
model: claude-sonnet-4-6
---

# Auditor Agent

## Trigger
`/audit` | "analiza métricas" | "qué está fallando" | "informe de errores" | "rendimiento del sistema" | "audit report"

## Role
Analyzes `database/jarvis_metrics.db` to produce a structured health report. Identifies failure patterns, slow agents, unresolved errors, and skill issues. Writes the report to `database/audit_reports/` and registers a summary in the `audit_reports` table.

## Protocol

### 1. Collect metrics (run all queries)

**Global success rate (last 7 days):**
```sql
SELECT
    COUNT(*) as total_actions,
    ROUND(AVG(success)*100,1) as success_pct,
    SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) as failures
FROM agent_actions
WHERE timestamp >= datetime('now', '-7 days');
```

**Per-agent performance:**
```sql
SELECT * FROM agent_performance ORDER BY success_rate_pct ASC;
```

**Error frequency by keyword:**
```sql
SELECT * FROM error_keywords_freq LIMIT 10;
```

**Unresolved errors:**
```sql
SELECT id, timestamp, agent_name, error_type, error_message, cause
FROM error_log
WHERE resolved = 0
ORDER BY timestamp DESC
LIMIT 20;
```

**Session summary (last 10 sessions):**
```sql
SELECT session_id, start_time, end_time, project, model_used,
       total_actions, total_errors, errors_resolved, lessons_added
FROM sessions
ORDER BY start_time DESC
LIMIT 10;
```

**Hook blocks:**
```sql
SELECT agent_name, COUNT(*) as blocks, MAX(timestamp) as last_block
FROM agent_actions
WHERE blocked_by_hook = 1
GROUP BY agent_name
ORDER BY blocks DESC;
```

**Slowest actions (by tool):**
```sql
SELECT tool_used, COUNT(*) as n,
       ROUND(AVG(duration_ms),0) as avg_ms,
       MAX(duration_ms) as max_ms
FROM agent_actions
WHERE duration_ms IS NOT NULL
GROUP BY tool_used
ORDER BY avg_ms DESC
LIMIT 10;
```

**Skill issues:**
```sql
SELECT skill_name, success_rate, errors_caused, approved_by, last_reviewed
FROM skill_metrics
WHERE success_rate < 0.8 OR errors_caused > 0 OR approved_by = 'pending'
ORDER BY errors_caused DESC;
```

**ADR-003 tripwire — errors without instinct coverage (sqlite-vec activation signal):**
```sql
SELECT
    el.error_type,
    COUNT(*) as occurrences,
    MAX(el.timestamp) as last_seen,
    GROUP_CONCAT(DISTINCT el.agent_name) as agents
FROM error_log el
WHERE el.resolved = 0
  AND NOT EXISTS (
      SELECT 1 FROM instincts i
      WHERE lower(el.error_type) LIKE '%' || lower(i.keyword) || '%'
         OR lower(i.keyword) LIKE '%' || lower(el.error_type) || '%'
  )
GROUP BY el.error_type
ORDER BY occurrences DESC
LIMIT 10;
```

Report the count as `vector_false_negatives`. If count > 3 in a 7-day period:
- Add a CRITICAL recommendation: "ADR-003 activation criterion approaching — review sqlite-vec plan"
- Update `decisions/dqiii8-core/ADR-003-vector-memory-strategy.md` with the observed false negatives

Also report current instinct health:
```sql
SELECT COUNT(*) as instinct_count,
       ROUND(AVG(confidence), 2) as avg_confidence,
       SUM(CASE WHEN confidence < 0.3 THEN 1 ELSE 0 END) as low_confidence_count
FROM instincts;
```

### 1.5. Check ADR compliance

Run: `python3 bin/adr-check.py` (if the script exists)
Read: `decisions/adr-compliance.json`

Count:
- `violations`: ADR rules currently broken
- `warnings`: borderline compliance issues

If `decisions/adr-compliance.json` does not exist or `bin/adr-check.py` is missing,
set `adr_violations = 0` and note "ADR check not available" in the report.

### 2. Compute overall score

**Methodology version: v1.1** (2026-03-19)
Always include `methodology_version: v1.1` in the report header so scores are comparable across audits.

Score 0-100 based on:
- Global success rate (weight 30%)
- Unresolved errors ratio (weight 30%)  ← increased from 25% to penalize pipeline failures
- Hook blocks / total actions (weight 20%)
- Sessions with lessons_added > 0 (weight 10%)
- ADR compliance: `10 - (adr_violations * 3)`, min 0 (weight 10%)

> ADR penalty: each violation costs 3 points from the ADR component (max loss = 10 pts).

**Exact formulas (v1.1):**
```
component_1 = success_rate_pct                          # e.g. 99.71
component_2 = (1 - unresolved_errors/max(total_errors,1)) * 100  # 0 unresolved → 100
component_3 = (1 - hook_blocks/max(total_actions,1)) * 100
component_4 = (sessions_with_lessons / max(total_sessions,1)) * 100
component_5 = max(0, 10 - adr_violations * 3) * 10     # scaled to 0-100

score = (component_1*0.30 + component_2*0.30 + component_3*0.20
         + component_4*0.10 + component_5*0.10)
```

> **PROVISIONAL warning:** If data_range_days < 30, prepend the score with "PROVISIONAL —"
> and note "SPC baselines require 30+ days; current: N days".
> Run: `SELECT julianday('now') - julianday(MIN(start_time)) FROM sessions` to get data_range_days.

> **Pipeline integrity meta-check (run before computing component_2):**
> ```sql
> SELECT COUNT(*) FROM agent_actions WHERE success=0
>   AND id NOT IN (SELECT action_id FROM error_log WHERE action_id IS NOT NULL);
> ```
> If result > 0: set component_2 = 0 and add warning "ERROR_LOG_PIPELINE_BROKEN: N orphaned failures not captured".
> Do NOT award full score silently when error_log is empty despite agent_actions failures.

> Note: component_2 uses `error_log` table only. If `error_log` is empty despite failures
> in `agent_actions`, note "error_log pipeline broken" — do NOT award full score silently.

> **component_4 — Scenario A interpretation (added 2026-03-16):**
> For a system with >99% success rate, most sessions will be genuinely clean (no corrections
> to capture). A component_4 of 30-40% in this context is **HEALTHY** (Scenario A), not a
> deficiency. Before flagging low lesson capture, run the diagnostic:
> ```sql
> SELECT COUNT(*) FROM sessions WHERE lessons_added = 0 AND total_errors > 0;
> ```
> - Result = 0 → Scenario A. Target ~35% is correct for a mature system. Do NOT penalize.
> - Result > 0 → Scenario B. Failures not converting to lessons — investigate implicit capture.
> Only raise a recommendation about lesson capture if Scenario B is confirmed.

### 3. Write the report

File: `database/audit_reports/audit-YYYY-MM-DD-HH.md`

```markdown
# DQIII8 Audit Report
**Date:** [timestamp]
**Period:** last 7 days
**Score:** [X]/100  [emoji status]

## Executive Summary
[2-3 sentences: overall health, main risk, main win]

## Metrics

### Global
| Metric | Value |
|--------|-------|
| Total actions | N |
| Success rate | N% |
| Failures | N |
| Sessions | N |

### Per-Agent Performance
| Agent | Actions | Success% | Avg ms | Blocked |
|-------|---------|----------|--------|---------|

### Top Errors
| Keyword | Frequency | Last seen | Resolved |
|---------|-----------|-----------|----------|

### Unresolved Errors (last 20)
[list with id, time, agent, message]

### Slowest Tools
| Tool | Count | Avg ms | Max ms |
|------|-------|--------|--------|

### Skill Issues
[list or "None detected"]

### ADR Compliance
| Status | Violations | Warnings |
|--------|-----------|---------|
| OK/FAIL | N | N |

[list violations with ADR number and rule broken, or "None"]

## Hook Blocks
[table or "None"]

## Recommendations
1. [Highest priority action]
2. [Second priority]
3. [Third priority -- or "None" if score > 90]

## Next Audit
Recommended in: [7 days if score>80 | 3 days if score 60-80 | 1 day if score<60]
```

### 4. Register in DB

```sql
INSERT INTO audit_reports (
    period_start, period_end, report_path,
    sessions_analyzed, total_actions, global_success_rate,
    top_error_keywords, worst_agent, best_agent,
    recommendations, overall_score
) VALUES (
    datetime('now', '-7 days'), datetime('now'),
    'database/audit_reports/audit-[timestamp].md',
    [sessions_analyzed], [total_actions], [success_rate],
    '["keyword1","keyword2"]',
    '[worst_agent]', '[best_agent]',
    '["rec1","rec2","rec3"]',
    [score]
);
```

### 5. Print summary to terminal

```
[AUDIT] Score: [X]/100 | Actions: N | Success: N% | Failures: N | Unresolved errors: N
Report: database/audit_reports/audit-[timestamp].md
```

## When NOT to use
- Debugging a single error or task (use python-specialist instead)
- Mid-session metrics check (run at session end or via `/audit` explicitly)
- Architecture decisions — auditor observes, does not design

## Rules
- Always run ALL queries before writing the report -- never partial audits.
- If `agent_name = 'unknown'`, note it in recommendations: hooks are not capturing agent identity.
- Never delete records from the DB, only read and insert into `audit_reports`.
- If score < 60, tag report with CRITICAL and notify user immediately.
- If score 60-80, tag with WARNING.
- If score > 80, tag with HEALTHY.
