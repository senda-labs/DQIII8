# PRO_CANDIDATES — Files Candidates for BSL/Pro Tier

When migrating to BSL (Business Source License) or a Pro tier,
these files contain the core proprietary IP of DQIII8.

## Current candidates

### Prompt Architect — `bin/agents/intent_amplifier.py`

Functions:
- `_build_prompt_tier_c()` — XML+CoT compact template for local models
- `_build_prompt_tier_b()` — Reference block template for 70B cloud
- `_build_prompt_tier_a()` — Data-only injection for frontier models
- `has_specific_data()` — Heuristic filter: specific data vs. generic definitions
- `filter_chunks_for_tier()` — Per-tier chunk selection and filtering

Why proprietary: tier-specific prompt construction is the core of the DQ
(Domain Quality) uplift. Benchmarks show +2.30 applied_sciences, +1.23
humanities_arts for Tier B; +3.19 natural_sciences, +4.11 social_sciences
for Tier C.

### Research Skill — `bin/tools/research_skill.py`

Importable API for autonomous research/verify/update/measure cycles.
Combines knowledge enrichment with structured output for agent loops.

## Future candidates (not yet built)

- **Auto-benchmark routing adaptativo** — online learning loop that adjusts
  tier routing weights based on benchmark_results feedback. Would use
  `v_dq_uplift` and `knowledge_benchmark_results` to retrain the classifier.

- **Cloud knowledge sync** — sync `knowledge/` dirs to a hosted vector store
  (Qdrant Cloud or Pinecone) for multi-instance deployments. Currently
  knowledge is local-only (`nomic-embed-text` + `index.json`).

## Notes

- All files remain MIT-licensed in the current public release.
- BSL transition (if it happens) restricts commercial use only; personal/
  research use stays free.
- Community contributions to these files require a CLA.
- Review date: 2026-Q3
