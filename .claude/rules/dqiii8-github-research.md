# DQIII8 — GitHub Research Tool

## Purpose
Research relevant GitHub repos for the DQIII8 stack.
Triggers: "search repos", "research GitHub", "does something exist that does X?"

## Priority topics
ffmpeg video automation, AI video generation, TTS synthesis Python,
subtitle generation, viral content generation

## Usage
Telegram command: `/github_research [topic] [min_stars]`
CLI: `python3 bin/github_researcher.py "[topic]" --min-stars 100 --max-repos 15`
Output: `tasks/github_reports/github_[topic]_[timestamp].md`
DB: `github_research` + `github_search_sessions` in dqiii8.db
Note: Without GITHUB_TOKEN → 60 req/h. Add to .env for 5000 req/h.
