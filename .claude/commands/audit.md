# /audit -- System Health Audit

Triggers the **auditor** agent to analyze `database/dqiii8.db` and produce a structured health report.

## Usage

```
/audit
/audit --period 30d       # analyze last 30 days instead of default 7
/audit --agent python-specialist   # scope to one agent
```

## What it does

1. Queries all metric tables: `agent_actions`, `error_log`, `sessions`, `skill_metrics`
2. Uses views `agent_performance` and `error_keywords_freq`
3. Computes an overall health score (0-100)
4. Writes a Markdown report to `database/audit_reports/audit-YYYY-MM-DD-HH.md`
5. Inserts a summary row in the `audit_reports` table
6. Prints a one-line summary to the terminal

## Output

```
[AUDIT] Score: 87/100 | Actions: 106 | Success: 100.0% | Failures: 0 | Unresolved errors: 0
Report: database/audit_reports/audit-2026-03-11-14.md
```

## Score interpretation

| Score | Status | Cadencia recomendada |
|-------|--------|----------------------|
| > 80  | HEALTHY | next audit in 7 days |
| 60-80 | WARNING | next audit in 3 days |
| < 60  | CRITICAL | next audit in 1 day, notify user |

## Auto-trigger

The `stop.py` hook automatically triggers `/audit` when 7+ days have passed since the last report in `audit_reports`.

## Agent

Handled by: `.claude/agents/auditor.md`
Model: `claude-sonnet-4-6`
