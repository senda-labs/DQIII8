# ADR-003 — Vector Memory Strategy (Deferred)

**Date:** 2026-03-16
**Status:** Accepted (Decision: Defer)
**Project:** jarvis-core
**Deciders:** Iker, JARVIS

---

## Context

JARVIS accumulates learned facts in two SQLite-backed structures:
- `vault_memory` table: 148 facts extracted from sessions (keyword, content, confidence)
- `instincts` table: 22 behavior patterns with boost/decay scoring (avg confidence 0.58)

All retrieval today is exact-match or full-scan SQL (`SELECT * FROM vault_memory WHERE keywords LIKE ?`).
As the knowledge base grows, semantic search becomes necessary — "find facts similar to X" without
exact keyword overlap.

Vector memory (sqlite-vec, pgvector, Chroma, or similar) would enable:
1. Semantic deduplication of lessons
2. Fuzzy instinct recall ("situations similar to this one")
3. Cross-session pattern detection without keyword dependency

The question is: when is this complexity justified?

## Decision

**Defer vector memory until the activation criterion is met.**

The system currently returns accurate results with exact-match SQL because the knowledge base
is small (148 facts, 22 instincts). Adding a vector index, embedding pipeline, and similarity
search layer before the data justifies it introduces operational complexity for zero user benefit.

**Activation criterion (measurable):**
> Activate vector memory when the auditor's instinct review query returns **more than 3 verified
> false negatives in a single 7-day audit period** — i.e., cases where an instinct or vault fact
> that should have been recalled for a given context was not, confirmed by post-hoc inspection.

This criterion is measurable via the audit process, not arbitrary, and forces the decision to
be driven by observed system degradation rather than speculative need.

**Technology choice at activation time:**
- First candidate: `sqlite-vec` (zero new infrastructure, embeds in existing jarvis_metrics.db)
- Embedding model: `nomic-embed-text` via Ollama (Tier-1, $0, local)
- Schema extension: add `embedding BLOB` column to `vault_memory` and `instincts`
- Fallback: keep exact-match SQL path active alongside vector path (dual-mode retrieval)

## Consequences

**Positive:**
- Zero operational overhead until criterion is met
- Criterion is auditable — appears in every audit report as "false negatives: N"
- When activated, sqlite-vec requires no new service, no Docker container, no API key
- Dual-mode retrieval guarantees backward compatibility

**Negative / Trade-offs:**
- Knowledge base may silently accumulate duplicate or near-duplicate facts before activation
- Exact-match retrieval will degrade as vault_memory grows past ~500 facts (estimated)
- The false-negative criterion requires manual verification — automated detection is hard

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| Activate now (sqlite-vec + nomic-embed-text) | 148 facts don't justify the complexity. Premature optimization. |
| Chroma or Qdrant as separate service | Requires a new daemon, port, Docker container. Too heavy for current scale. |
| pgvector via Postgres migration | Requires migrating off SQLite. ADR-002 mandates SQLite for jarvis_metrics.db. |
| Never activate (stay SQL-only) | Not viable long-term. At 500+ facts, exact-match becomes unreliable. |
| Time-based trigger (e.g., "after 6 months") | Arbitrary. The false-negative metric is a better signal than calendar time. |

---

## Invariants

No machine-checkable invariants for a deferred decision. The criterion is tracked manually
via the audit process.

**Audit checklist item (add to auditor.md when criterion approaches):**
```sql
-- Run at each audit to track false negative pressure:
SELECT COUNT(*) as instinct_count,
       AVG(confidence) as avg_confidence,
       SUM(CASE WHEN confidence < 0.3 THEN 1 ELSE 0 END) as low_confidence
FROM instincts;
```
When `instinct_count > 50` AND `low_confidence > 5`, begin false-negative verification manually.

---

*Reviewed and accepted 2026-03-16. Next review trigger: instinct_count > 50.*
