---
name: weekly-review
description: Generate weekly dashboard update — reads sessions from the last 7 days, queries metrics from dqiii8.db, regenerates 00_DASHBOARD.md locally. Local-only artifact — never committed or pushed.
command: /weekly-review
allowed-tools: [Bash, Read, Write]
user-invocable: true
---

# /weekly-review — Weekly Dashboard Update

## Trigger
User writes `/weekly-review` (typically on Mondays or Fridays).

> **Path audit 2026-08-17 (Gap 14).** Three of this skill's path literals were
> wrong and the skill could not complete end-to-end: `projects/*.md` never
> existed (the real project corpus is `my-projects/`), `00_DASHBOARD.md` is
> gitignored (deliberately — it was purged from the public repo in commit
> `1437942`), and `sessions/` is gitignored too. The git push step has been
> removed accordingly: this is a **local-only** artifact, same convention as
> `/handover`.

## Behavior

### 1. Read sessions from the last 7 days

`sessions/` holds `YYYY-MM-DD_session_N.md` files written by `/handover`. Select
by **filename date**, not mtime — mtimes are churned by git operations and
backups, so they are not a reliable recency signal:

```bash
CUTOFF=$(date -d '7 days ago' +%Y-%m-%d)
ls /root/dqiii8/sessions/*.md \
  | awk -v c="$CUTOFF" -F/ '{
        d = substr($NF, 1, 10)
        if (d ~ /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/ && d >= c) print
    }' \
  | sort
```

The date-shape guard matters: `sessions/` also holds a few legacy files that do
not start with a date (`SESSION-20260529-netcup.md`, `pending_message_batch_api.md`),
and a plain string comparison sorts those *above* any `2026-…` name, pulling
them into every week. Note the original `find … -newer <(date -d '7 days ago')`
never worked at all — `-newer` compares against a **file's** mtime, and the
process-substitution FIFO is created now, so the predicate matched zero files on
every run.

Session notes have **no YAML frontmatter**. Each is a handover note with
`# Session Handover — YYYY-MM-DD` and `##` sections (`Operador`,
`Last 5 commits`, `Uncommitted changes`, `Tests`, `Active services`,
`Next steps`). Extract the date from the heading and the first bullet of
`## Next steps` as the one-liner.

### 2. Read the status of all projects

The project corpus is `my-projects/`:

- `my-projects/PROJECT.md` — the index. A markdown table with columns
  `Proyecto | Estado | Descripción | Próximo paso`, split across
  "Proyectos Activos" and "Proyectos en Diseño / Stalled" sections. This is the
  fastest source for the dashboard's status table.
- `my-projects/<slug>/PROJECT.md` — per-project detail. Status lives on a plain
  header line (`Status: active | Stack: ...`), **not** in YAML frontmatter.

Prefer the index; fall back to the per-project files only when the index looks
stale relative to a session note from this week.

### 3. Query week metrics

```sql
SELECT COUNT(*), SUM(total_actions), SUM(total_errors), MAX(end_time)
FROM sessions WHERE start_time >= datetime('now', '-7 days');

SELECT agent_name, COUNT(*) as n FROM agent_actions
WHERE timestamp >= datetime('now', '-7 days')
GROUP BY agent_name ORDER BY n DESC LIMIT 3;
```

Run against `/root/dqiii8/database/dqiii8.db` (full path — no aliases in
non-interactive shells).

### 4. Regenerate `00_DASHBOARD.md`

Written at the repo root. The file is gitignored and may not exist yet on a
fresh checkout — write it unconditionally, do not read-then-patch.

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

### 5. Do NOT commit or push

`00_DASHBOARD.md` and `sessions/` are both gitignored, and the dashboard was
deliberately purged from the public repo (it aggregates private project status).
`git add` on either path fails or silently no-ops; forcing it with `-f` would
re-leak the content that purge removed. The dashboard stays local.

### 6. Feedback
```
[WEEKLY] Dashboard updated locally · Week W[N] · [N] sessions processed
```

## Notes
- Use `date +%V` for the ISO week number
- The dashboard is the only file this skill completely regenerates
- If there were no sessions that week, say so explicitly in the dashboard
- `$DQIII8_ROOT` is not exported in every shell — use `/root/dqiii8` or
  `${DQIII8_ROOT:-/root/dqiii8}`, never a bare `$DQIII8_ROOT`
