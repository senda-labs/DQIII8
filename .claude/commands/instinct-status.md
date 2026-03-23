---
name: instinct-status
description: Shows learned instincts from dqiii8.db, grouped by project and confidence.
allowed_tools: ["Bash"]
---

# /instinct-status — Instinct Status

Shows continuous learning instincts stored in `dqiii8.db`.

## Usage

```
/instinct-status
/instinct-status --project dqiii8-core
/instinct-status --top 10
```

## What it does

1. Reads the `instincts` table from `database/dqiii8.db`
2. Groups by project (project-scoped first, then global)
3. Shows confidence bar + times applied
4. Highlights high-confidence instincts (>0.7) as "consolidated"

## Implementation

```bash
python3 -c "
import sqlite3, os, sys

DB = 'database/dqiii8.db'
project_filter = None
top_n = 20

# Parse args (passed as ARGS env or argv)
args = sys.argv[1:]
for i, a in enumerate(args):
    if a == '--project' and i+1 < len(args):
        project_filter = args[i+1]
    if a == '--top' and i+1 < len(args):
        top_n = int(args[i+1])

conn = sqlite3.connect(DB)

if project_filter:
    rows = conn.execute(
        'SELECT keyword, pattern, confidence, times_applied, times_successful, project, created_at '
        'FROM instincts WHERE project=? ORDER BY confidence DESC LIMIT ?',
        (project_filter, top_n)
    ).fetchall()
else:
    rows = conn.execute(
        'SELECT keyword, pattern, confidence, times_applied, times_successful, project, created_at '
        'FROM instincts ORDER BY project, confidence DESC LIMIT ?',
        (top_n,)
    ).fetchall()

conn.close()

if not rows:
    print('No instincts registered yet.')
    print('They will be generated automatically at the end of sessions with corrections in tasks/lessons.md')
    exit(0)

def conf_bar(c):
    filled = int(c * 10)
    return '█' * filled + '░' * (10 - filled) + f'  {int(c*100)}%'

print('=' * 60)
print(f'  INSTINCT STATUS — {len(rows)} total')
print('=' * 60)

current_proj = '__none__'
for kw, pattern, conf, applied, successful, proj, created in rows:
    if proj != current_proj:
        current_proj = proj
        label = proj if proj else 'GLOBAL'
        print(f'\n## {label.upper()}')
    bar = conf_bar(conf or 0)
    success_pct = int((successful or 0) / max(applied or 1, 1) * 100)
    tag = ' ✅ consolidated' if (conf or 0) >= 0.7 else ''
    print(f'  {bar}  [{kw}]{tag}')
    print(f'    applied: {applied or 0}x  successful: {success_pct}%  since: {(created or \"\")[:10]}')
    if pattern:
        preview = pattern[:80] + ('...' if len(pattern) > 80 else '')
        print(f'    {preview}')
"
```

## Expected output

```
============================================================
  INSTINCT STATUS — 5 total
============================================================

## DQIII8-CORE
  ████████░░  80%  [nested-claude] ✅ consolidated
    applied: 3x  successful: 100%  since: 2026-03-12
    [2026-03-12] [nested-claude] use claude CLI inside session → use OpenRouter

## GLOBAL
  █████░░░░░  50%  [encoding]
    applied: 1x  successful: 0%  since: 2026-03-12
```

## Notes

- Source: `database/dqiii8.db` table `instincts`
- Updated in each stop.py when there are new lessons in `tasks/lessons.md`
- Lesson format for parsing: `[YYYY-MM-DD] [KEYWORD] cause → fix`
- To view full history: `python3 -c "import sqlite3; ..."`
