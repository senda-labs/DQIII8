# DQIII8 — Internal Tools Reference

## CLI tools (direct invocation)
| Script | Purpose | Trigger |
|--------|---------|---------|
| `bin/tools/gemini_export.py` | Export module for Gemini review | `/gemini_export [module]` |
| `bin/tools/gemini_review.py` | Register Gemini feedback in DB | Post-review |
| `bin/tools/github_researcher.py` | Search relevant GitHub repos | `/github_research [topic]` |
| `bin/tools/orphan_finder.py` | Detect unreferenced scripts | `python3 bin/tools/orphan_finder.py` |
| `bin/core/validate_env.py` | Verify .env keys at startup | Called by `bin/j.sh` |

## Knowledge system
Agents with knowledge base: `finance-analyst`, `python-specialist`
```bash
python3 bin/agents/knowledge_search.py --agent python-specialist "async patterns"
```
Knowledge: `.claude/agents/{agent}/knowledge/*.md` + `index.json`

## GitHub Research
```bash
python3 bin/github_researcher.py "[topic]" --min-stars 100 --max-repos 15
```
Output: `tasks/github_reports/`. Without GITHUB_TOKEN → 60 req/h.

## Telegram
```python
from bin.core.notify import send_telegram; send_telegram("msg")
from bin.core.notify import send_document; send_document(path, caption="…")
```
Commands: `/cc <prompt>`, `/cc_status`, `/auth_status`
Auth: OAuth via `~/.claude/.credentials.json`. Bot: `bin/ui/dqiii8_bot.py`
