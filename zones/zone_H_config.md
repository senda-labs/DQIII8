# Zone H — Config
> Updated: 2026-06-02

---

## What it covers
All configuration: `config/`, `.claude/rules/`, `.obsidian/`, domain maps, tiering table.

---

## config/

| File | Role |
|---|---|
| `config/claude_settings_template.json` | Claude Code settings template |
| `config/domain_agent_map.json` | Domain → agent routing map |
| `config/intelligence_sources.json` | Intelligence data sources |

**NEVER hardcode values from `config/`** — always load via `os.environ.get()` or config reader.

---

## .claude/rules/ (always read before acting)

| File | When to read |
|---|---|
| `00_core_behavior.md` | Always — zero-complacency, scope, cost-first |
| `01_database_mutations.md` | Any DB/SQL/sqlite3 work |
| `02_hooks_and_permissions.md` | Hooks, PermissionAnalyzer |
| `03_tiering_and_routing.md` | Tier/routing/agent changes |
| `DYNAMIC.md` | Injected by rules_dispatcher at runtime |
| `rules_db/git-safety.md` | Git/Bash operations |
| `rules_db/dqiii8-error-prevention.md` | Recurring error prevention |

---

## Tiering Table (summary)

| Tier | Provider | Model | Cost |
|---|---|---|---|
| C | Ollama | local | $0 |
| B | Groq | mixtral/llama | $0 |
| B+ | GitHub Models | — | $0 |
| A | Anthropic | Sonnet 4.6 | ~$0.03 |
| S | Anthropic | Opus 4.8 | ~$0.20 |

Full algorithm → `.claude/rules/03_tiering_and_routing.md`

---

## .obsidian/

Obsidian vault config. `.obsidian/` is gitignored — local only.

---

## Cross-zone Links
- Rules loaded by hooks → [[zone_B_extensions]]
- Tiering used by pipeline router → [[zone_A_core_pipeline]]
