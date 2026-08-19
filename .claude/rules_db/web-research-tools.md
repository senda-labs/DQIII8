# Web & Research Tool Routing — DQIII8

Firecrawl MCP integration: `.mcp.json` → `firecrawl` server, backed by `firecrawl-mcp`.

## Fetch vs. scrape (start cheap, escalate on failure)

1. **Default**: `mcp__fetch` (Python `mcp_server_fetch`) — $0, static HTML → markdown.
2. **Escalate to `firecrawl scrape` (CLI skill)** only when `mcp__fetch` returns empty,
   blocked, or the page is JS-rendered / behind anti-bot. Firecrawl scrape costs credits.

## One lane per capability — CLI is primary for everything except research

`firecrawl-cli` (scrape/search/crawl/map/interact/parse/agent/monitor) is the primary
path for all of those. The `firecrawl` MCP server duplicates the same tool names, plus
research-only tools not exposed by the CLI at all.

**Use the MCP `firecrawl_research_*` tools only for literature/paper-finding tasks**
(search_papers, related_papers — citation-graph traversal via similar/citers/references
modes, inspect_paper, read_paper). This is the only capability in the whole DQIII8 tool
surface that does citation-graph work; nothing else substitutes for it.

For everything else (scrape/search/crawl/map/interact/parse/agent/monitor), use the CLI
skill: **this is now enforced, not a preference.** Desde 2026-08-18 los 21 firecrawl MCP
no-research están en `permissions.deny` de `.claude/settings.json` — llamarlos falla, no
degrada. Solo los `firecrawl_research_*` siguen permitidos.

## Search credit refund — CLI only

`firecrawl search` (CLI) cuesta 2 créditos por llamada. El refund de 1 crédito vía
`firecrawl_search_feedback` era un tool MCP y **hoy está denegado**: no lo intentes, no hay
ruta de refund desde una sesión de agente. (Tope histórico: 100/equipo/día UTC.)
