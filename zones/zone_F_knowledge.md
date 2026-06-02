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
