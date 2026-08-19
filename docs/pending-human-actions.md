# Pending human actions

Items that require a human edit outside any agent session. Agents must NOT apply these
themselves, and must NOT attempt to bypass the block by any tool.

## 1. Deny the non-research firecrawl MCP tools in `.claude/settings.json` — ✅ DONE 2026-08-18

**Applied.** The 21 tools below are present in `permissions.deny` in `.claude/settings.json`.
Kept here as the record of what was pasted and why; no action outstanding.

Rationale: `firecrawl-cli` is the primary lane for scrape/search/crawl/map/interact/parse/
agent/monitor; the `firecrawl` MCP server duplicates those tool names and double-counts
credits. Only the MCP `firecrawl_research_*` tools are irreplaceable (citation-graph work).

This cannot be a single glob — every firecrawl MCP tool shares the
`mcp__firecrawl__firecrawl_*` prefix, including the research tools that must stay allowed —
so the denied tools have to be enumerated.

`.claude/settings.json` is a blocked-write path (`02_hooks_and_permissions.md`): no agent may
edit it under any circumstance, including to narrow permissions. A human must paste the block
below into `permissions.deny` by hand.

```json
"deny": [
  "mcp__firecrawl__firecrawl_crawl", "mcp__firecrawl__firecrawl_check_crawl_status",
  "mcp__firecrawl__firecrawl_agent", "mcp__firecrawl__firecrawl_agent_status",
  "mcp__firecrawl__firecrawl_extract", "mcp__firecrawl__firecrawl_interact",
  "mcp__firecrawl__firecrawl_interact_stop", "mcp__firecrawl__firecrawl_map",
  "mcp__firecrawl__firecrawl_monitor_create", "mcp__firecrawl__firecrawl_monitor_update",
  "mcp__firecrawl__firecrawl_monitor_delete", "mcp__firecrawl__firecrawl_monitor_get",
  "mcp__firecrawl__firecrawl_monitor_list", "mcp__firecrawl__firecrawl_monitor_check",
  "mcp__firecrawl__firecrawl_monitor_checks", "mcp__firecrawl__firecrawl_monitor_run",
  "mcp__firecrawl__firecrawl_parse", "mcp__firecrawl__firecrawl_scrape",
  "mcp__firecrawl__firecrawl_search", "mcp__firecrawl__firecrawl_search_feedback",
  "mcp__firecrawl__firecrawl_feedback"
]
```

Moved out of `.claude/rules_db/web-research-tools.md` on 2026-08-18 (finding F6, panel-6
context-economy audit): it was 475 tokens injected on every web call for an action no agent
is allowed to take.
