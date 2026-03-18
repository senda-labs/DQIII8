# JARVIS — Auditoría Externa (Gemini Pro)

## Flujo
1. Iker detecta área de mejora (viralidad, rendimiento, arquitectura)
2. Claude Code implementa → ejecuta `/gemini_export [módulo] --metric [métrica]`
3. Iker pega el `.md` en Gemini Pro 2.5 Flash Thinking
4. Gemini responde → Iker copia feedback de vuelta
5. Claude Code aplica correcciones → registra en `gemini_audits` (DB)

## Tabla: jarvis_metrics.db → gemini_audits
Campos: `module, metric, report_path, question, gemini_response,
issues_found, issues_resolved, impact_score, applied_to_code, notes`

## Uso
Comando Telegram: `/gemini_export [módulo]` (full|script|audio|video|subtitles)
Script: `bin/gemini_export.py --metric [viralidad|rendimiento|arquitectura] --question "..."`
Output: `tasks/gemini_reports/gemini_[módulo]_[timestamp].md`
