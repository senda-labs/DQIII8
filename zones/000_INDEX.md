# 000_INDEX — dqiii8 Attention Router
> Reading this file routes you to the correct zone in <5 seconds. Stay under 250 lines.
> Updated: 2026-06-16

---

## 1. SYSTEM STATE

| Component | Value |
|---|---|
| Server | VPS server · `YOUR_VPS_IP` · SSH alias `your-vps` |
| Telegram UI | @YourBotName |
| CLI | `j cc` / `j loop` / `j status` |
| DB | `database/dqiii8.db` (46T + 20V live) · `dqiii8_metrics.db` |
| Pipeline | 7-step DQ: Classify → Retrieve → Gate → Amplify → Route → Execute → Memory |
| Hooks | 15 · Skills: 20 · Agents: 17 |
| Repos | public: `senda-labs/DQIII8` · premium: `senda-labs/DQIII8-premium` |

**Active projects:** intl-reports (tanda5 pendiente) · content-automation · accounting-erp · ouroboros-q-eml

---

## 2. ZONE MAP

| Zone | File | Covers |
|---|---|---|
| A | [[zone_A_core_pipeline]] | DQ 7-step pipeline, openrouter_wrapper, director.py, bin/agents/, bin/core/ |
| B | [[zone_B_extensions]] | .claude/ — agents (17), skills (19), hooks (14), rules engine |
| C | [[zone_C_database]] | dqiii8.db (46T+20V), dqiii8_metrics.db, schema_v2.sql, var/ |
| D | [[zone_D_infrastructure]] | VPS, SSH, Telegram bot (bin/ui/), infrastructure/ACTIVE.md |
| E | [[zone_E_projects]] | my-projects/ — 9 active + archived, status, entry points |
| F | [[zone_F_knowledge]] | docs/, knowledge/, ADRs, CHANGELOG, architecture decisions |
| G | [[zone_G_tasks]] | tasks/ — audit, benchmarks, research, results, FULL_SYSTEM_MAP |
| H | [[zone_H_config]] | config/, .claude/rules/, .obsidian/, tiering table |
| I | [[zone_I_ops]] | sessions/, uploads/, examples/, tests/ |

---

## 3. DECISION TREE

```
Question about...
├── pipeline not running / routing / tier selection / prompt flow   → zone_A
├── agents / skills / hooks / rules / permissions                   → zone_B
├── DB tables / SQL / schema / sqlite3 / metrics                    → zone_C
├── VPS / SSH / server / Telegram bot / deployment                  → zone_D
├── a specific project (intl-reports, pokemon, etc.)               → zone_E
├── docs / ADRs / architecture / knowledge base                     → zone_F
├── tasks / benchmarks / audits / research / system map            → zone_G
├── config / .env / domain_agent_map / tiering rules               → zone_H
├── sessions / uploads / logs / tests / examples                    → zone_I
└── routing / state / what to work on next                         → HERE (000_INDEX)
```

---

## 4. INVARIANTS (never violate)

1. **Cost-First**: C (Ollama $0) → B (Groq $0) → B+ (GitHub $0) → A (Sonnet) → S (Opus). Never use A/S for B tasks.
2. **ANTHROPIC_API_KEY must be `""`** in subprocess env when using Claude Code OAuth.
3. **NEVER** write to `.env`, `CLAUDE.md`, `database/schema.sql` from generated code.
4. **NEVER** commit `*.db` files — gitignored. Use `database/schema_v2.sql` for fresh installs.
5. **DENY from PermissionAnalyzer is final** — do not retry or bypass.
6. **Plans ≥3 modules or ambiguous scope → enter plan mode first**, wait for confirmation.
7. **Destructive/irreversible actions** (rm -rf, DROP, force-push) → STOP, notify user, wait.
8. **tasks/audit/ path is hardcoded** in red-team, blue-team, security-cycle skills — never rename.

---

## 5. ENTRY POINTS

```bash
# Telegram bot
j cc               # Claude Code session
j loop             # autonomous loop
j status           # system status

# Pipeline direct
python bin/core/openrouter_wrapper.py --prompt "..."

# Plan compiler (opt-in: DQ_COMPILE_HOOK=1)
python3 -m bin.core.dq_compile "prompt"

# DB
sqlite3 database/dqiii8.db ".tables"
sqlite3 database/dqiii8_metrics.db ".tables"

# Claude Code
claude             # starts session (OAuth, no API key needed)
```

---

## 6. LINK GRAPH

```
000_INDEX --> zone_A (pipeline entry)
000_INDEX --> zone_D (server state)
000_INDEX --> zone_E (active projects)
zone_A --> zone_C (DB writes)
zone_A --> zone_B (agent/skill calls)
zone_B --> zone_H (rules/config)
zone_C --> zone_F (schema docs)
zone_D --> zone_A (bot → pipeline)
zone_E --> zone_F (project ADRs)
zone_G --> zone_B (audit skill refs)
zone_H --> zone_B (rules loaded by hooks)
zone_I --> zone_G (session outputs → tasks)
```

Max useful traversal: 2 hops from INDEX. Stop there.

---

## 7. HOW TO USE THIS VAULT (30-second context recovery)

**Read order:**
1. **`000_INDEX.md`** — this file — routing + invariants (~500 tok)
2. **One zone file** matching your question (~800 tok)
3. **`SESSION.md`** — current handover state (~200 tok)
4. **At most 1 wikilink hop** if the answer spans zones
5. **Stop** — recovery at ~1,500 tokens total

> Do NOT read all zone files. Do NOT scan the repo blindly.
> Route via this index, then grep.
