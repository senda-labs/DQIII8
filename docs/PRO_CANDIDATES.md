# PRO_CANDIDATES — Files Candidates for BSL/Pro Tier

When migrating to BSL (Business Source License) or a Pro tier,
these files contain the core proprietary IP of DQIII8.

## Tier C — Prompt Architect (intent_amplifier.py)

**File:** `bin/agents/intent_amplifier.py`

**Functions:**
- `_build_prompt_tier_c()` — XML+CoT compact template for local models
- `_build_prompt_tier_b()` — Reference block template for 70B cloud
- `_build_prompt_tier_a()` — Data-only injection for frontier models
- `has_specific_data()` — Heuristic filter: specific data vs. generic definitions
- `filter_chunks_for_tier()` — Per-tier chunk selection and filtering

**Why proprietary:** The tier-specific prompt construction is the core of
the DQ (Domain Quality) uplift. Benchmarks show +2.30 (applied_sciences),
+9.29 overall for Tier B. This is the differentiating IP.

## Tier B — Research Skill (research_skill.py)

**File:** `bin/tools/research_skill.py`

**Why proprietary:** Importable API for autonomous research/verify/update/measure
cycles. Combines knowledge enrichment with structured output for agent loops.

## Notes

- These files remain MIT-licensed in the current public release.
- The BSL transition (if it happens) would restrict commercial use only.
- Community contributions to these files require a CLA.
- Review date: 2026-Q3
