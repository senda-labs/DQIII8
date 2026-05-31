# /svsi-review — Pre-revisión Semántica de Informes

## Usage
/svsi-review {slug}              # modo interactivo en sesión Claude Code
/svsi-review --batch {file}      # delega a pre_drive_review.py (tmux, no en sesión)
/svsi-review --stats             # métricas acumuladas desde SQLite

## What it does
1. Invoca `tools.review.engine.review_slug({slug})` — 11 rules deterministas
2. Escribe `companies/{slug}/review/review_report.{json,md}`
3. Para cada issue, según `remediation`:
   - `surgical_edit` → propone Edit concreto usando `edit_hint`, pide confirmación, aplica
   - `regen_section` → genera `data/svsi_handoff_{slug}.txt` con comando tmux
   - `human_review` → marca para consultor ANOVA
   - `dismiss_only` → muestra para info, registra si se confirma FP
4. Re-render: `python3 scripts/render_batch.py --slug {slug} --doc-type plan --force`
5. Re-valida (max 3 iteraciones)
6. Persiste resoluciones en SQLite (`pipeline.db`)

## Modos de uso disponibles
- `/svsi-review empresa-sl` → revisión interactiva de una empresa
- `python3 scripts/pre_drive_review.py --slug-list data/tanda3_slugs.txt` → batch shadow (desde tmux)
- `python3 scripts/pre_drive_review.py --mode gate --slug-list ...` → batch gate (desde tmux)

## Restricciones
- CLAUDECODE=1 bloquea orchestrator — `regen_section` requiere tmux externo
- Máximo 3 iteraciones de corrección por empresa
- Nunca editar `report_content_*.json` sin confirmación explícita del usuario
- Nunca llamar `core.cli run/resume` — bloqueado por CLAUDECODE=1
