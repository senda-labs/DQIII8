# Zone F — Knowledge & Docs
> Updated: 2026-06-02

---

## What it covers
Documentation, knowledge base, ADRs, changelog, and architecture decisions.

---

## docs/

| File | Role |
|---|---|
| `docs/CHANGELOG.md` | System changelog |
| `docs/DQIII8_PLUGIN_DESIGN.md` | Plugin design spec |
| `docs/architecture_decision_context_efficiency.md` | ADR-001 (linked from CLAUDE.md) |
| `docs/superpowers/specs/` | SDD spec files |

---

## knowledge/

Vector knowledge base used by the RAG pipeline (zone A).
- Chunks embedded via `bin/core/embeddings.py` (nomic-embed-text)
- Retrieved by `bin/agents/knowledge_enricher.py`
- Public knowledge in `senda-labs/DQIII8`, premium in `senda-labs/DQIII8-premium`

Inventory (`ls knowledge/`):

| Path | Contents |
|---|---|
| `knowledge/AUDIT_REPORT.md` | Knowledge-base audit notes |
| `knowledge/README.md` | KB overview |
| `knowledge/applied_sciences/` | Domain corpus |
| `knowledge/formal_sciences/` | Domain corpus |
| `knowledge/humanities_arts/` | Domain corpus |
| `knowledge/natural_sciences/` | Domain corpus |
| `knowledge/social_sciences/` | Domain corpus |

Organized by top-level academic domain (matches the domain classifier taxonomy in zone A). Agent-scoped knowledge also lives under `.claude/agents/{agent}/knowledge/` (e.g. finance-specialist: dcf_methodology, financial_ratios, wacc_fundamentals + index.json).

---

## Key Architecture Decisions

| ADR | File | Decision |
|---|---|---|
| ADR-001 | `docs/architecture_decision_context_efficiency.md` | Context efficiency architecture |

---

## Repos

| Repo | Contents |
|---|---|
| `senda-labs/DQIII8` (public) | `bin/`, `tests/`, `knowledge/`, `.claude/agents/`, `docs/` |
| `senda-labs/DQIII8-premium` (private) | Bilingüe classifier, benchmark infra, premium knowledge |

Premium layer applied via `overlay.sh` in `/root/dqiii8-workspace/`.

---

## Cross-zone Links
- DB schema docs → [[zone_C_database]]
- Project ADRs → [[zone_E_projects]]
