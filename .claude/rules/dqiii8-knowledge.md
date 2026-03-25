# DQIII8 — Knowledge System

Agentes con knowledge base: `finance-analyst`, `python-specialist`.

```bash
python3 bin/agents/knowledge_search.py --agent python-specialist "async patterns"
python3 bin/agents/knowledge_indexer.py --agent python-specialist
```

Knowledge dirs: `.claude/agents/{agent}/knowledge/*.md` + `index.json`
Domain lens: `bin/agents/domain_lens.py` — enrich system prompt con chunks del índice.
Intent amplifier: `bin/agents/intent_amplifier.py` — confidence gate 0.55, subdomain classifier.
