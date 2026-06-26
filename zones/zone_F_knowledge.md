# Zone F — Knowledge & Docs
> Updated: 2026-06-26

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

## Dispatch Bridge (CC ↔ dqiii8)

| Componente | Ruta | Función |
|-----------|------|---------|
| `bin/core/dispatch.py` | dqiii8 root | Módulo + CLI para despachar a NIM/Groq desde CC |
| `.claude/skills/dispatch-agent/SKILL.md` | dqiii8 root | Skill: `/dispatch-agent` — Hermes Work Loop pattern |
| `tasks/results/` | dqiii8 root | Resultados JSON de dispatches (sync+async) |
| `tasks/queue/` | dqiii8 root | Cola async bidireccional |
| `bin/autonomous_loop.sh` | dqiii8 root | Canal dqiii8→CC (ya existía: `claude -p`) |

Patrón Hermes: CC orquesta → `dispatch_parallel()` a N agentes NIM/Groq → CC recolecta → Opus valida si crítico.

---

## Provider Research

| Doc | Fecha | Contenido |
|-----|-------|-----------|
| `docs/research/2026-06-26-nvidia-nim-investigation.md` | 2026-06-26 | Sondeo completo NIM (52/121 modelos), deep research 107 agentes, routing integrado |

Reglas operacionales: `.claude/rules_db/nim-provider.md`

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

## football-value — Decisiones de modelado (2026-06-20)

| Decisión | Rationale |
|---|---|
| Dixon-Coles xG-adjusted (rho=0 en xG/hybrid) | τ-correction solo válida para conteos enteros |
| neutral_venue=True para todo WC2026 | Todos los partidos en sede neutral |
| Bootstrap σ_λ (n=200, seed=42) | Epistemic uncertainty; n_bootstrap=0 → no apostar |
| Elo + Transfermarkt prior (0.7/0.3) | Transfermarkt supera FIFA rank para predicción internacional (Peeters 2018) |
| Ridge regularization (default 0.1) | Previene colapso de λ con datos WC escasos (16 partidos inicial) |
| fair_edge > 0.05 threshold | De-vigged; raw edge sobrestima EV en 5-7% |
| adjusted_kelly_fraction = raw_kf / (1 + σ_avg²) | Shrinkage automático de stake bajo incertidumbre alta |

---

## Cross-zone Links
- DB schema docs → [[zone_C_database]]
- Project ADRs → [[zone_E_projects]]
