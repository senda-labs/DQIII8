---
name: weekly-review
description: Generate weekly dashboard update — reads sessions from last 7 days, queries metrics from dqiii8.db, regenerates 00_DASHBOARD.md, commits and pushes.
command: /weekly-review
allowed-tools: [Bash, Read, Write]
user-invocable: true
---

# /weekly-review — Weekly Dashboard Update

## Trigger
User writes `/weekly-review` (typically on Mondays or Fridays).

## Behavior

### 1. Read sessions from the last 7 days
```bash
find $DQIII8_ROOT/sessions/ -name "*.md" -newer <(date -d '7 days ago' +%Y-%m-%d) | sort
```
For each session: extract frontmatter (project, date) and "What we did" section (first bullet).

### 2. Read status of all projects
Read `projects/*.md` — extract: title, status from YAML frontmatter, section "Next step".

### 3. Query week metrics
```sql
SELECT COUNT(*), SUM(total_actions), SUM(total_errors), MAX(end_time)
FROM sessions WHERE start_time >= datetime('now', '-7 days');

SELECT agent_name, COUNT(*) as n FROM agent_actions
WHERE timestamp >= datetime('now', '-7 days')
GROUP BY agent_name ORDER BY n DESC LIMIT 3;
```

### 4. Regenerate `00_DASHBOARD.md`

```markdown
---
title: DQIII8 Dashboard
date_updated: YYYY-MM-DD HH:MM
week_number: W[N] YYYY
---

# DQIII8 Dashboard

## Project Status
| Project | Status | Latest progress | Next step |
|---------|--------|-----------------|-----------|

## Sessions this week
- YYYY-MM-DD · [project] — [1-liner]

## Metrics
| Metric | Value |
|--------|-------|
| Total sessions | N |
| Success rate | N% |
| Most used agent | [name] (N actions) |
```

### 5. Git push
```bash
git -C $DQIII8_ROOT add 00_DASHBOARD.md sessions/
git -C $DQIII8_ROOT commit -m "docs: weekly review week W[N]"
git -C $DQIII8_ROOT push origin main
```

### 6. Feedback
```
[WEEKLY] Dashboard updated · Week W[N] · [N] sessions processed
```

## Notes
- Use `date +%V` for the ISO week number
- The dashboard is the only file that weekly-review completely regenerates
- If no sessions that week, indicate it explicitly in the dashboard
