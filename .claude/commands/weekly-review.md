# /weekly-review — Weekly Dashboard Update

## Trigger
User writes `/weekly-review` (typically on Mondays or Fridays).

## Behavior

### 1. Read sessions from the last 7 days
```bash
find $JARVIS_ROOT/sessions/ -name "*.md" -newer <(date -d '7 days ago' +%Y-%m-%d) | sort
```
For each session: extract frontmatter (project, date) and "What we did" section (first bullet).

### 2. Read status of all projects
Read `projects/*.md` — extract: title, status from YAML frontmatter, section "Next step".

### 3. Query week metrics
```sql
-- Sessions this week
SELECT COUNT(*), SUM(total_actions), SUM(total_errors), MAX(end_time)
FROM sessions
WHERE start_time >= datetime('now', '-7 days');

-- Most used agent
SELECT agent_name, COUNT(*) as n
FROM agent_actions
WHERE timestamp >= datetime('now', '-7 days')
GROUP BY agent_name ORDER BY n DESC LIMIT 3;

-- Global success rate
SELECT ROUND(AVG(success)*100,1) FROM agent_actions
WHERE timestamp >= datetime('now', '-7 days');
```

### 4. Regenerate `00_DASHBOARD.md`

```markdown
---
title: DQIII8 Dashboard
date_updated: YYYY-MM-DD HH:MM
week_number: W[N] YYYY
tags: [dashboard, weekly]
---

# DQIII8 Dashboard
**Updated:** YYYY-MM-DD · Week W[N]

## Project Status

| Project | Status | Latest progress | Next step |
|---------|--------|-----------------|-----------|
| [[project-name]] | 🟢 Active | [1-liner] | [next step] |
| [[project-name]] | 🟡 Active | [1-liner] | [next step] |
| [[project-name]] | 🔵 Paused | [1-liner] | [next step] |
| [[dqiii8-core]] | 🟢 Active | [1-liner] | [next step] |

## Sessions this week

- **YYYY-MM-DD** · [project] — [1-liner of what was done]
- ...

## Metrics

| Metric | Value |
|--------|-------|
| Total sessions | N |
| Total actions | N |
| Success rate | N% |
| Most used agent | [name] (N actions) |
| Last audit score | N/100 |

## Pending tasks

> [!todo] [project-name]
> - [ ] [task 1]
> - [ ] ...

## Alerts

> [!warning] [Only if audit score < 80 or unresolved errors]
> [Problem description]
```

### 5. Git push
```bash
git -C $JARVIS_ROOT add 00_DASHBOARD.md sessions/
git -C $JARVIS_ROOT commit -m "docs: weekly review week W[N]"
git -C $JARVIS_ROOT push origin main
```

### 6. Feedback
```
[WEEKLY] ✅ Dashboard updated in 00_DASHBOARD.md · Week W[N] · [N] sessions processed
```

## Notes
- Use `date +%V` for the ISO week number
- If there are no sessions that week, indicate it explicitly in the dashboard
- The dashboard is the only file that weekly-review completely regenerates
