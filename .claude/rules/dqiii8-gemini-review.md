# DQIII8 — External Audit (Gemini Pro)

## Flow
1. Identify an area for improvement (virality, performance, architecture)
2. Claude Code implements → runs `/gemini_export [module] --metric [metric]`
3. Paste the `.md` into Gemini Pro 2.5 Flash Thinking
4. Gemini responds → copy feedback back
5. Claude Code applies corrections → registers in `gemini_audits` (DB)

## Table: dqiii8.db → gemini_audits
Fields: `module, metric, report_path, question, gemini_response,
issues_found, issues_resolved, impact_score, applied_to_code, notes`

## Usage
Telegram command: `/gemini_export [module]` (full|script|audio|video|subtitles)
Script: `bin/gemini_export.py --metric [virality|performance|architecture] --question "..."`
Output: `tasks/gemini_reports/gemini_[module]_[timestamp].md`
