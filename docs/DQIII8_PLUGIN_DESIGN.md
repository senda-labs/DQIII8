# DQIII8 — Claude Code Plugin Design

> Design document. NOT for implementation yet.
> Created: 2026-03-29

## 1. What DQIII8 offers that OMC doesn't

| Capability | OMC | DQIII8 Plugin |
|------------|-----|---------------|
| Multi-agent orchestration | Yes (20 agents) | No (OMC covers this) |
| Domain classification | No | Yes (5 domains, bge-m3 embeddings) |
| Knowledge enrichment | No | Yes (5 domain indexes, 1024d vectors) |
| Ecomode tier routing | Haiku/Sonnet/Opus | C(Ollama)/B(Groq)/A(Sonnet)/S(Opus) |
| Project detection from prompt | No | Yes (keyword centroids) |
| Telegram bot integration | Slack/Discord | Telegram |
| Local LLM fallback | No | Yes (Ollama qwen2.5-coder:7b) |
| Cost: $0 tier | No (Haiku ~$0.001) | Yes (Ollama + Groq = $0.000) |

## 2. Minimum Viable Plugin

### Skills to export

| Skill | Purpose |
|-------|---------|
| `/dqiii8:audit` | System health check (DB, agents, pipelines) |
| `/dqiii8:checkpoint` | Save session state with git commit |
| `/dqiii8:enrich` | Inject domain knowledge into prompt |
| `/dqiii8:route` | Classify prompt tier (C/B/A/S) |

For the current active skills catalogue, see [[skills-registry/INDEX|Skills Registry]].

### Hooks to export

| Hook | Event | Purpose |
|------|-------|---------|
| PermissionAnalyzer | PreToolUse | APPROVE/DENY/ESCALATE tool calls |
| session_start | SessionStart | Context injection (CLAUDE.md + PROJECT.md) |
| stop | Stop | Auto-commit + lessons learned |

### Agents to expose

The 9 active DQIII8 agents as subagent types:
- python-specialist, git-specialist, code-reviewer, orchestrator
- content-automator, data-analyst, creative-writer, auditor, research-analyst

## 3. Technical Approach: MCP Server in Python

Claude Code plugins are Node.js/TypeScript. DQIII8 is Python — see [[bin/README|Script Catalog]] for all available Python modules.

**Option A: TypeScript wrapper** — TS shim calls Python scripts via child_process.
- Pro: native plugin format
- Con: two languages, maintenance burden

**Option B: Python MCP server** — expose DQ functions via MCP protocol.
- Pro: single language, reuses existing code directly
- Con: requires MCP server setup in plugin manifest

**Recommendation: Option B** — Python MCP server.

### Architecture

```
Claude Code <--MCP--> dqiii8-mcp-server.py <--> dqiii8.db
                                           <--> knowledge/
                                           <--> bin/agents/
                                           <--> bin/core/
```

### MCP Server Tools

```python
# Tools exposed via MCP
@tool("dqiii8_enrich")
def enrich(prompt: str, domain: str = "auto") -> str:
    """Enrich prompt with domain knowledge chunks."""

@tool("dqiii8_classify")
def classify(prompt: str) -> dict:
    """Classify prompt: domain, tier, project, confidence."""

@tool("dqiii8_audit")
def audit() -> str:
    """Run system health audit, return scored report."""

@tool("dqiii8_search_knowledge")
def search_knowledge(query: str, domain: str, top_k: int = 5) -> list:
    """Vector search across domain knowledge base."""
```

### Plugin Manifest (package.json)

```json
{
  "name": "dqiii8",
  "version": "0.1.0",
  "claude-code-plugin": {
    "mcpServers": {
      "dqiii8": {
        "command": "python3",
        "args": ["${PLUGIN_ROOT}/mcp_server.py"],
        "env": {
          "DQIII8_ROOT": "${PLUGIN_ROOT}"
        }
      }
    },
    "skills": ["skills/*.md"],
    "hooks": "hooks/hooks.json",
    "agents": ["agents/*.md"]
  }
}
```

## 4. For users without Claude subscription

| Scenario | What works | What doesn't |
|----------|------------|--------------|
| Standalone (Groq+Ollama) | Full pipeline, Telegram bot, all agents | No Claude Code integration |
| Plugin (Claude Code) | Everything above + skills, hooks, MCP tools | Requires Claude subscription |

install.sh handles standalone. Plugin adds Claude Code layer on top.

## 5. Timeline Estimate

| Phase | Scope | Effort |
|-------|-------|--------|
| Phase 1 | MCP server with enrich + classify + search | 1 day |
| Phase 2 | Plugin manifest + skills export | 1 day |
| Phase 3 | Hooks export (PermissionAnalyzer) | 0.5 day |
| Phase 4 | Testing + docs | 0.5 day |
| **Total** | **MVP** | **3 days** |

## 6. Open Questions

1. Should the plugin require Ollama installed? Or fall back to Groq-only?
2. Should knowledge indexes ship with the plugin or be built on first use?
3. How to handle .env secrets in plugin context? (MCP env vars vs dotenv)
4. Should PermissionAnalyzer run in plugin mode or only standalone?
