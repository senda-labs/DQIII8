# Changelog

## v0.1.0-beta (2026-03-23)

### Features

- 5-layer DQ pipeline: classify → enrich → amplify → route → execute
- 3-tier model routing: local (Ollama) → free cloud (Groq/Together AI) → paid (Anthropic)
- Domain knowledge base with 894 verified chunks across 5 domains
- Prompt Architect: per-tier and per-intent prompt restructuring
- Task relevance reranking for knowledge retrieval (intent+entity second pass)
- Confidence gate: selective RAG — skips enrichment when model already knows the material
- Working memory: SQLite-backed session context across prompts
- 26 specialized agents with domain routing
- Telegram bot integration (/cc command — run any prompt via Telegram)
- Autonomous loop with Telegram reporting
- SPC-based self-auditing system
- 91 tests, 0 failures

### Known Limitations

- CPU-only: `qwen2.5-coder:7b` timeouts on non-code tasks — use Groq/llama for those
- No web dashboard UI yet (planned for v0.2.0)
- Session memory has 24h TTL (configurable via `cleanup_old_sessions(hours=N)`)
- `hierarchical_router.py` centroid agents field stale — does not affect main pipeline
