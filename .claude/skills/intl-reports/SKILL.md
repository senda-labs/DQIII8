---
name: intl-reports
description: Genera y entrega informes de internacionalización (Diagnóstico + Plan) para pymes españolas. Batch pipeline via Orchestrator v4 (core.cli) desde tmux externo. NUNCA empresa-a-empresa con Agent Haiku manual.
command: /intl-reports
allowed-tools: [Bash, Agent, Read, Write, Edit, Glob, Grep]
user-invocable: true
---

# /intl-reports — Orquestador de Informes de Internacionalización

Proyecto en `/root/dqiii8/my-projects/intl-reports/`.
CSV tanda3: `data/3a tanda empresas 201 P&L 28 abril.csv` (201 empresas).

## Arquitectura

**Orchestrator v4** (`core.cli`) = pipeline completo por empresa, vía `claude --print` subprocess.
**NUNCA** lanzar desde Claude Code activo (`CLAUDECODE=1` bloquea con error explícito).
**Siempre** desde terminal/tmux externo:

```bash
env -u CLAUDECODE python3 -m core.cli run --slug {slug} --concurrency 6
```

## Pipeline batch (modo producción)

```bash
# Batch secuencial desde tmux externo — NO desde Claude Code
bash scripts/batch_run_tanda3.sh data/tanda3_run_ready.txt
```

El script:
1. Salta empresas con ambos DOCXs ya existentes (>500 KB c/u)
2. Detecta estado parcial → `resume`; empresa fresh → `run`
3. Para en `exit 2` si detecta rate limit (reanudar después)
4. Flags: `--concurrency 6 --skip-brief`

### Waves del Orchestrator v4

```
Wave -2  crawler auto          skip si dossier < 30d
Wave -1  implications_brief    auto [Haiku], --skip-brief lo omite si ya existe
Wave  0  strategic + diag_intro + diag_areas×6   [8 en paralelo]
Wave  1  market_signals_layer + diag_conclusions
Wave  2  plan_body_org + plan_body_financial
Wave  3  plan_body_governance + plan_body_entry
Wave  4  plan_body_marketing
Wave  5  markets + plan_body_recommendations
Post     QA → auto_qa_fixer → DOCX → Telegram
```

## Prerrequisitos por empresa (gate real del pipeline)

```
A. SABI_Export_*.xls         info-origin/              financiero (empleados, revenue)
B. raw_survey_data.json      info-origin/              cuestionario ANOVA (auto USIL)
C. ssot.json                 data/                     fuente canónica (reemplaza content_brief.json, eliminado en B7)
D. company_intelligence.json data/                     REQUERIDO para pasar ACIS gate (completeness ≥85%)
   └── generado por cobrowsing session:
       python3 scripts/cobrowsing_batch.py --slug-list data/tanda3_no_acis.txt
       (Chrome human-in-the-loop, CDP :9222, TUI interactiva)
```

## ACIS Gate (core/preflight.py) — bloqueador real

Gate bloquea si `completeness < 85`. Scoring (11 puntos totales):

| Componente | Puntos | Fuente |
|---|---|---|
| Identity (name + cnae + sector) | 3 | meta.json / ssot.json |
| Financial (employees ×2 + revenue ×2) | 4 | matrix resolver |
| Survey | 2 | raw_survey_data.json |
| company_intelligence signals | 1 | data/company_intelligence.json |
| osint data | 1 | info-origin/market_intel.json |

Sin `company_intelligence.json`: 9/11 = **81.8% → FAIL**.
Con `company_intelligence.json`: 10/11 = **90.9% → PASS**.

```bash
# Diagnóstico gate sin ejecutar
python3 scripts/acis_dry_run.py --slug {slug}

# Override peligroso (solo si calidad 81.8% es aceptable)
python3 -m core.cli run --slug {slug} --skip-gate
```

## Estado de producción (2026-05-21)

| Métrica | Valor |
|---|---|
| CSV tanda3 total | 201 empresas |
| Ambos DOCXs completos | **130** |
| Excluidas pervasive_no_intent | 6 |
| Pendientes (sin company_intel) | **65** — `data/tanda3_no_acis.txt` |
| Errores técnicos en batch | 0 |

**Pendientes 65 — path para completarlas:**

```bash
# 1. Cobrowsing session (Chrome CDP, human-in-the-loop) — genera company_intelligence.json
python3 scripts/cobrowsing_batch.py --slug-list data/tanda3_no_acis.txt

# 2. Verificar gate pasa tras cobrowsing
python3 scripts/acis_dry_run.py --slug {slug}

# 3. Batch producción (desde tmux externo, NO desde Claude Code)
bash scripts/batch_run_tanda3.sh data/tanda3_no_acis.txt
```

## Status y diagnóstico

```bash
# Estado de una empresa
python3 -m core.cli status --slug {slug}

# Estado del batch completo (tanda3)
python3 -c "
from pathlib import Path
slugs = [l.strip() for l in open('data/tanda3_slugs.txt') if l.strip() and not l.startswith('#')]
for slug in slugs:
    d = Path('companies') / slug / 'drafts'
    diag = any(d.glob('*diagnostico*.docx')) if d.exists() else False
    plan = any(d.glob('*plan*.docx')) if d.exists() else False
    st = 'DONE' if (diag and plan) else ('PARTIAL' if (diag or plan) else 'PENDING')
    if st != 'DONE': print(f'{st:8} {slug}')
"

# ACIS gate batch check
python3 scripts/pre_batch_check.py --show-failures
```

## Directorio de trabajo

```
/root/dqiii8/my-projects/intl-reports/
├── data/
│   ├── 3a tanda empresas 201 P&L 28 abril.csv   ← CSV tanda3 (201 empresas)
│   ├── tanda3_slugs.txt                          ← 136 procesados en batch anterior
│   ├── tanda3_run_ready.txt                      ← subconjunto listo para run
│   └── tanda3_no_acis.txt                        ← 65 pendientes (sin company_intel)
├── companies/{slug}/
│   ├── meta.json                                 ← perfil empresa
│   ├── orchestrator_state.db                     ← SQLite WAL (runs/tasks/sections)
│   ├── info-origin/
│   │   ├── raw_survey_data.json                  ← cuestionario ANOVA
│   │   ├── company_intelligence.json             ← señales cobrowsing (también en data/)
│   │   └── SABI_Export_*.xls                     ← financiero SABI
│   └── data/
│       ├── ssot.json                             ← fuente canónica (reemplaza content_brief.json)
│       ├── company_intelligence.json             ← REQUIRED para ACIS gate
│       ├── implications_brief.txt                ← auto Wave -1
│       ├── report_content_diagnostic.json
│       └── report_content_plan.json
├── drafts/  ← ¡OJO! los DOCX están en companies/{slug}/drafts/ (fuera de data/)
│   └── {slug}_diagnostico.docx
│   └── {slug}_plan_internacionalizacion.docx
├── scripts/
│   ├── batch_run_tanda3.sh                       ← batch producción tanda3
│   ├── cobrowsing_batch.py                       ← genera company_intelligence.json
│   ├── acis_dry_run.py                           ← diagnóstico ACIS sin ejecutar
│   └── pre_batch_check.py                        ← validación pre-batch
└── tools/
    ├── acis_validation_layer.py
    ├── auto_qa_fixer.py
    └── intel/
        ├── session.py                            ← cobrowsing human-in-the-loop
        └── web_presence_runner.py                ← Playwright batch (requiere web_url en ssot)
```

## QA Gate (10 checks integrados en v4)

| # | Check | Tipo |
|---|---|---|
| 1 | No placeholders (`[PENDIENTE]`, `TODO`, `TBD`) | Hard |
| 2 | Word counts (≥ ceiling×0.65, floor 40w) | Hard |
| 3 | Country consistency | Hard |
| 4 | Radar coherence | Hard |
| 5 | PESTEL market coherence | Hard |
| 6–10 | Redundancy, competitor usage, DAFO, entry coherence, repetición | Soft |

Auto-fix pre-QA: `tools/auto_qa_fixer.py` (6 patches + `fix_plan()`).
Max 2 retries Haiku por sección. Soft failures: no bloquean DOCX.

## Errores frecuentes

| Error | Solución |
|---|---|
| `ACIS GATE BLOCKED — completeness 81.8` | Ejecutar cobrowsing session → genera company_intelligence.json |
| `ssot.json missing` | `python3 -m tools.ssot.ssot_builder --slug {slug}` |
| `Credit balance too low` | OAuth — `ANTHROPIC_API_KEY` debe ser `""` en subprocess |
| `CLAUDECODE=1 blocks` | Lanzar desde tmux externo, NUNCA desde Claude Code activo |
| Rate limit en batch | Esperar, relanzar script (salta automáticamente las ya completadas) |

## Reglas absolutas

1. **NUNCA** lanzar `core.cli run/resume` desde Claude Code activo.
2. **NUNCA** usar `anthropic` SDK ni subprocess LLM directo.
3. **NUNCA** modificar archivos en `tools/` — corregir el JSON de contenido, no el validador.
4. **NUNCA** declarar éxito sin verificar que el DOCX existe en `drafts/` con tamaño >500 KB.
5. `--skip-gate` solo si completeness ≥80% y no hay tiempo para cobrowsing (documenta el tradeoff).
6. `content_brief.py` eliminado en B7 — no existe. La fuente canónica es `ssot.json`.
