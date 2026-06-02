# Zone A — Core Pipeline
> Updated: 2026-06-02

---

## What it covers
The DQ 7-step processing pipeline: from raw prompt to model response.
Entry: `bin/core/openrouter_wrapper.py` | Director: `bin/director.py`

---

## Pipeline Flow

```
prompt
  ↓ [1] CLASSIFY    bin/agents/domain_classifier.py   → classify_domain()
  ↓ [2] RETRIEVE    bin/agents/knowledge_enricher.py  → get_relevant_chunks()
  ↓ [3] GATE        bin/agents/confidence_gate.py     → should_enrich()
  ↓ [4] AMPLIFY     bin/agents/intent_amplifier.py    → amplify()
  ↓ [5] ROUTE       bin/core/openrouter_wrapper.py    → tier/model selection
  ↓ [6] EXECUTE     Ollama:11434 / Groq / Anthropic
  ↓ [7] MEMORY      bin/agents/working_memory.py      → save_exchange()
```

---

## Key Files

`bin/agents/` holds 21 modules. Core pipeline (the 7 steps above):

| File | LOC | Role |
|---|---|---|
| `bin/core/openrouter_wrapper.py` | 934 | Entry point, multi-provider router, full DQ pipeline |
| `bin/agents/domain_classifier.py` | 710 | [1] Domain + confidence classification |
| `bin/agents/knowledge_enricher.py` | 250 | [2] RAG chunk retrieval |
| `bin/agents/confidence_gate.py` | 64 | [3] Gate: should RAG run? |
| `bin/agents/intent_amplifier.py` | 791 | [4] Prompt enrichment per tier |
| `bin/agents/working_memory.py` | 121 | [7] SQLite session memory |
| `bin/director.py` | — | Orchestrates multi-step tasks |
| `bin/core/ollama_wrapper.py` | 126 | Tier C (local) wrapper |
| `bin/core/auth_watchdog.py` | — | OAuth / API key watchdog |

Routing / classification helpers:

| File | LOC | Role |
|---|---|---|
| `bin/agents/hierarchical_router.py` | 680 | Domain→subdomain→agent routing tree |
| `bin/agents/subdomain_classifier.py` | 392 | Subdomain refinement under a domain |
| `bin/agents/domain_agent_selector.py` | 88 | Maps domain → specialist agent |
| `bin/agents/domain_lens.py` | 127 | Domain-specific prompt framing |

Knowledge / RAG support (feeds step [2]):

| File | LOC | Role |
|---|---|---|
| `bin/agents/hybrid_search.py` | 474 | Hybrid vector + keyword retrieval |
| `bin/agents/vector_store.py` | 424 | Embedding store + similarity search |
| `bin/agents/knowledge_indexer.py` | 206 | Builds/updates the knowledge index |
| `bin/agents/knowledge_search.py` | 130 | Query interface over the index |
| `bin/agents/chunk_freshness_reviewer.py` | 376 | Flags stale chunks for re-embedding |
| `bin/agents/key_facts_generator.py` | 289 | Extracts key facts from chunks |
| `bin/agents/key_facts_multikey_batch.py` | 252 | Batch key-fact extraction (multi-key) |

Memory / learning:

| File | LOC | Role |
|---|---|---|
| `bin/agents/temporal_memory.py` | 470 | Time-decayed long-term memory |
| `bin/agents/memory_decay.py` | 218 | Decay scheduler for stored memories |
| `bin/agents/instinct_evolver.py` | 155 | Evolves learned instincts (see instinct-status) |
| `bin/agents/template_loader.py` | 82 | Loads prompt/response templates |

---

## Tier Routing (Cost-First)

| Tier | Provider | Cost | When |
|---|---|---|---|
| C | Ollama (local) | $0 | Default start |
| B | Groq | $0 | C fails or task complexity |
| B+ | GitHub Models | $0 | Extended B |
| A | Anthropic Sonnet | ~$0.03 | Explicit A-task |
| S | Anthropic Opus | ~$0.20 | Explicit S-task only |

Full table → `[[zone_H_config]]` → `.claude/rules/03_tiering_and_routing.md`

---

## Key Functions

```python
# domain_classifier.py
classify_domain(prompt) → (domain, confidence, method)

# intent_amplifier.py
amplify(prompt) → {amplified, tier, domain, action, entity, chunks_used}

# openrouter_wrapper.py
main()  # full pipeline
stream_response()
log_to_db()
```

---

## bin/ Layout

`ls bin/` — top-level operational dirs not covered above:

| Path | Contents |
|---|---|
| `bin/core/` | Wrappers (openrouter, ollama), db.py, auth/security, pipeline core |
| `bin/agents/` | 21 pipeline + routing + RAG + memory modules (see Key Files) |
| `bin/monitoring/` | analytics_collector, audit_trigger, health_watchdog, ml_selector, routing_analyzer, cost_tracker, weekly_audit, subscription |
| `bin/tools/` | gemini_review, knowledge_harvester, benchmark_*, github_researcher, db_init, sqlite_mcp, handover, summarize/truncate_output, etc. (+ `_archived/`) |
| `bin/workspace/` | launch scripts: launch_swarm.sh, launch_beeswarm.sh, launch_monitor.sh |
| `bin/ui/` | Telegram bot (`dqiii8_bot.py`) — see [[zone_D_infrastructure]] |
| `bin/` (root) | director.py, orchestrator.py, bee_swarm.py, j.sh, nightly.sh, autonomous_loop.sh, plugin_manager.py |

---

## Cross-zone Links
- DB writes → [[zone_C_database]]
- Agent/skill calls from pipeline → [[zone_B_extensions]]
- Telegram bot → pipeline entry → [[zone_D_infrastructure]]
