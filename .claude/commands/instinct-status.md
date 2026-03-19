---
name: instinct-status
description: Muestra instincts aprendidos desde jarvis_metrics.db, agrupados por proyecto y confianza.
allowed_tools: ["Bash"]
---

# /instinct-status — Estado de Instincts

Muestra los instincts de aprendizaje continuo almacenados en `jarvis_metrics.db`.

## Uso

```
/instinct-status
/instinct-status --project dqiii8-core
/instinct-status --top 10
```

## Qué hace

1. Lee la tabla `instincts` de `database/jarvis_metrics.db`
2. Agrupa por proyecto (project-scoped primero, luego globales)
3. Muestra barra de confianza + veces aplicado
4. Destaca instincts con alta confianza (>0.7) como "consolidados"

## Implementación

```bash
python3 -c "
import sqlite3, os, sys

DB = '/root/dqiii8/database/jarvis_metrics.db'
project_filter = None
top_n = 20

# Parse args (pasados como ARGS env o argv)
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
    print('No hay instincts registrados aún.')
    print('Se generarán automáticamente al final de sesiones con correcciones en tasks/lessons.md')
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
    tag = ' ✅ consolidado' if (conf or 0) >= 0.7 else ''
    print(f'  {bar}  [{kw}]{tag}')
    print(f'    aplicado: {applied or 0}x  exitoso: {success_pct}%  desde: {(created or \"\")[:10]}')
    if pattern:
        preview = pattern[:80] + ('...' if len(pattern) > 80 else '')
        print(f'    {preview}')
"
```

## Output esperado

```
============================================================
  INSTINCT STATUS — 5 total
============================================================

## DQIII8-CORE
  ████████░░  80%  [nested-claude]{tag}
    aplicado: 3x  exitoso: 100%  desde: 2026-03-12
    [2026-03-12] [nested-claude] usar claude CLI dentro de session → usar OpenRouter

## GLOBAL
  █████░░░░░  50%  [encoding]
    aplicado: 1x  exitoso: 0%  desde: 2026-03-12
```

## Notas DQIII8

- Fuente: `database/jarvis_metrics.db` tabla `instincts`
- Se actualiza en cada stop.py cuando hay lecciones nuevas en `tasks/lessons.md`
- Formato de lección para ser parseada: `[YYYY-MM-DD] [KEYWORD] causa → fix`
- Para ver historial completo: `python3 -c "import sqlite3; ..."`
