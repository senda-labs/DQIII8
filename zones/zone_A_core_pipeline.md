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

| File | LOC | Role |
|---|---|---|
| `bin/core/openrouter_wrapper.py` | 934 | Entry point, multi-provider router, full DQ pipeline |
| `bin/agents/domain_classifier.py` | 710 | Domain + confidence classification |
| `bin/agents/intent_amplifier.py` | 791 | Prompt enrichment per tier |
| `bin/agents/knowledge_enricher.py` | 250 | RAG chunk retrieval |
| `bin/agents/confidence_gate.py` | 64 | Gate: should RAG run? |
| `bin/agents/working_memory.py` | 121 | SQLite session memory |
| `bin/director.py` | — | Orchestrates multi-step tasks |
| `bin/core/ollama_wrapper.py` | 126 | Tier C (local) wrapper |
| `bin/core/auth_watchdog.py` | — | OAuth / API key watchdog |

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

## Cross-zone Links
- DB writes → [[zone_C_database]]
- Agent/skill calls from pipeline → [[zone_B_extensions]]
- Telegram bot → pipeline entry → [[zone_D_infrastructure]]
