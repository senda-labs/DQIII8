---
name: audit
description: Run complete system health audit of DQIII8 — checks DB integrity, agent performance, pipeline connections, error log, and services. Produces a scored Markdown report.
command: /audit
allowed-tools: [Bash, Read, Grep]
user-invocable: true
auto-invoke:
  - when: "7+ days since last audit OR 3+ unresolved errors detected in session"
    action: "Run /audit automatically to surface problems"
---

# /audit -- System Health Audit

Triggers the **auditor** agent to analyze `database/dqiii8.db` and produce a structured health report.

## Usage

```
/audit
/audit --period 30d       # analyze last 30 days instead of default 7
/audit --agent python-specialist   # scope to one agent
```

## Scope note — `sessions` / `morning_report` / `loop_effectiveness`

`.claude/hooks/stop.py:439` writes `sessions` from every CLI session
(`INSERT ... ON CONFLICT(session_id) DO UPDATE`), gated on
`_total_actions > 0` (`stop.py:436`). So `sessions` is only populated when
`agent_actions` has ≥1 row for that session, which makes a near-empty
`sessions` table a **second, independent detector for an `agent_actions`
outage** — a real signal to chase, not noise to dismiss. Only `morning_report`
is genuinely bot-only (written solely by `bin/ui/dqiii8_bot.py`).

`loop_effectiveness` is a VIEW over `objectives`, which has 0 rows because the
autonomous-loop execution flow (`bin/director.py` loop mode) isn't in active
use yet — an empty result there is still expected, not a symptom to chase.

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

The `stop.py` hook automatically triggers `/audit` when 7+ days have passed since the last report in `audit_reports`. Also auto-invoked when errors accumulate during a session.

## Agent

Handled by: `.claude/agents/auditor.md`
Model: `claude-sonnet-5`
