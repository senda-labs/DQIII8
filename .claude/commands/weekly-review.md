# /weekly-review — Weekly Dashboard Update

## Trigger
User writes `/weekly-review` (typically on Mondays or Fridays).

## Behavior

> **SSOT: `.claude/skills/weekly-review/SKILL.md`.** This command file duplicated
> the same three broken path literals and was corrected alongside it on
> 2026-08-17 (Gap 14). Keep the two in sync; the skill carries the full rationale.

### 1. Read sessions from the last 7 days
```bash
CUTOFF=$(date -d '7 days ago' +%Y-%m-%d)
ls ${DQIII8_ROOT:-/root/dqiii8}/sessions/*.md \
  | awk -v c="$CUTOFF" -F/ '{
        d = substr($NF, 1, 10)
        if (d ~ /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/ && d >= c) print
    }' | sort
```
Select by filename date, not mtime. (The previous `find … -newer <(date …)` matched
zero files on every run: `-newer` compares against a file's mtime and the
process-substitution FIFO is created *now*.)

Session notes have no YAML frontmatter — they are `/handover` notes with
`# Session Handover — YYYY-MM-DD` and `##` sections. Use the heading for the date
and the first bullet of `## Next steps` for the one-liner.

### 2. Read status of all projects
Read `my-projects/PROJECT.md` — the index table (`Proyecto | Estado | Descripción |
Próximo paso`). Per-project detail lives in `my-projects/<slug>/PROJECT.md`, where
status is a plain `Status: active | Stack: …` header line, not YAML frontmatter.
(`projects/*.md` does not exist and never did.)

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

### 5. Do NOT commit or push
`00_DASHBOARD.md` and `sessions/` are both gitignored, and the dashboard was
deliberately purged from the public repo (commit `1437942`) because it aggregates
private project status. `git add` on either path fails or no-ops; forcing it with
`-f` would re-leak exactly what that purge removed. The dashboard stays local,
same convention as `/handover`.

### 6. Feedback
```
[WEEKLY] ✅ Dashboard updated locally in 00_DASHBOARD.md · Week W[N] · [N] sessions processed
```

## Notes
- Use `date +%V` for the ISO week number
- If there are no sessions that week, indicate it explicitly in the dashboard
- The dashboard is the only file that weekly-review completely regenerates
