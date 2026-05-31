---
name: svsi
description: >
  Pre-revisión semántica de informes de internacionalización antes de subir al Drive compartido.
  Detecta inconsistencias entre cuestionario, diagnóstico y plan. Propone correcciones focales
  (surgical_edit) en sesión o genera handoff para tmux (regen_section).
  Trigger: "revisa el informe de X", "pre-review X", "checkea X antes de Drive", "/svsi-review X".
command: /svsi-review
allowed-tools: [Bash, Read, Edit, Grep]
user-invocable: true
---

# /svsi-review — Pre-revisión Semántica de Informes

Proyecto: `/root/dqiii8/my-projects/intl-reports/`
Plan canónico: `docs/SVSI_PLAN.md` (v1.3)
Engine: `tools/review/engine.py` → `review_slug(slug)`
Reporter: `tools/review/reporter.py` → `write_report(report)`

## Cuándo usar

- Antes de subir un informe al Drive de ANOVA
- Cuando un consultor pida verificar un informe específico
- Para detectar inconsistencias que `qa_pre_render` existente no captura
- Trigger explícito: "revisa {slug}", "/svsi-review {slug}", "pre-review {slug}"

## Cuándo NO usar

- Para verificar la generación misma (eso lo hace `qa_pre_render` dentro del pipeline)
- Para regenerar secciones (eso requiere tmux externo con `core.cli`)
- Para batch overnight (usar `scripts/pre_drive_review.py` desde tmux externo)

## Flujo en sesión (Interactive Mode)

**Paso 1 — Ejecutar engine:**
```bash
cd /root/dqiii8/my-projects/intl-reports
python3 -c "
from tools.review.engine import review_slug
from tools.review.reporter import write_report
report = review_slug('{slug}')
write_report(report)
print(f'Verdict: {report.summary[\"verdict\"]}  C={report.summary[\"critical\"]}  H={report.summary[\"high\"]}  issues={len(report.issues)}')
"
```

**Paso 2 — Leer report estructurado:**
```bash
cat companies/{slug}/review/review_report.json
```

**Paso 3 — Para cada issue, según `remediation`:**

| remediation | Acción en sesión |
|-------------|-----------------|
| `surgical_edit` | Proponer Edit usando `edit_hint.path` + `edit_hint.new_template`. Pedir confirmación. Aplicar. |
| `regen_section` | Mostrar `handoff_command`. Escribir `data/svsi_handoff_{slug}.txt`. NO ejecutar. |
| `human_review` | Mostrar al usuario para decisión manual del consultor ANOVA. |
| `dismiss_only` | Mostrar como informativo. Preguntar si registrar como FP. |

**Paso 4 — Re-render DOCX** (solo si se aplicaron surgical_edits):
```bash
python3 scripts/render_batch.py --slug {slug} --doc-type plan --force
```

**Paso 5 — Re-validar** (máximo 3 iteraciones del loop):
```bash
python3 -c "
from tools.review.engine import review_slug
report = review_slug('{slug}')
print(f'Nuevo verdict: {report.summary[\"verdict\"]}')
for i in report.issues:
    print(f'  {i.rule_id} {i.severity}: {i.title}')
"
```

**Paso 6 — Reportar al usuario:**
- N issues resueltos quirúrgicamente (surgical_edits aplicados)
- M issues en handoff a tmux (comando exacto)
- K issues para consultor ANOVA
- Estado final: PASS/WARN/FAIL

## Restricciones absolutas

- NUNCA ejecutar `core.cli run/resume` — CLAUDECODE=1 bloquea el orchestrator
- NUNCA editar `tools/agent_writer.py`, `tools/block_writer.py`, `core/`
- NUNCA declarar "informe listo" sin verificar que el DOCX tiene > 500 KB
- Las correcciones se proponen y confirman antes de aplicar — no edición silenciosa
- Máximo 3 iteraciones del loop detect → edit → re-render → re-validate

## Comandos de referencia

```bash
# Engine + reporter (una empresa)
python3 -c "from tools.review.engine import review_slug; from tools.review.reporter import write_report; r=review_slug('{slug}'); write_report(r)"

# Ver report MD generado
cat companies/{slug}/review/review_report.md

# Re-render DOCX tras surgical_edit
python3 scripts/render_batch.py --slug {slug} --doc-type plan --force

# Batch shadow desde tmux (NO en Claude Code)
python3 scripts/pre_drive_review.py --slug-list data/tanda3_slugs.txt

# Stats acumuladas
python3 scripts/pre_drive_review.py --stats

# Marcar FP
python3 scripts/pre_drive_review.py --mark-fp {issue_id} --note "motivo"
```
