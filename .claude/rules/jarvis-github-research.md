# JARVIS — GitHub Research Tool

## Propósito
Investigar repos GitHub relevantes para el stack JARVIS.
Triggers: "busca repos", "investiga GitHub", "¿existe algo que haga X?"

## Tópicos prioritarios
ffmpeg video automation, AI video generation, TTS synthesis Python,
subtitle generation, viral content generation

## Uso
Comando Telegram: `/github_research [topic] [min_stars]`
CLI: `python3 bin/github_researcher.py "[topic]" --min-stars 100 --max-repos 15`
Output: `tasks/github_reports/github_[topic]_[timestamp].md`
DB: `github_research` + `github_search_sessions` en jarvis_metrics.db
Nota: Sin GITHUB_TOKEN → 60 req/h. Añadir a .env para 5000 req/h.
