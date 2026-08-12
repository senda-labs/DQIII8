# Web & Research Tool Routing — DQIII8

Added 2026-07-02 after Opus 4.8 review of the firecrawl MCP integration
(`.mcp.json` → `firecrawl` server, backed by `firecrawl-mcp`).

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

For everything else (scrape/search/crawl/map/interact/parse/agent/monitor), prefer the
CLI skill over the MCP tool of the same name — avoids double-counting credits and keeps
one obvious tool per job.

Recommended (not yet applied — requires a human edit to the protected
`.claude/settings.json`, see note below): deny the non-research firecrawl MCP
tools so this preference is enforced, not just documented. This cannot be a
single glob — every firecrawl MCP tool shares the `mcp__firecrawl__firecrawl_*`
prefix (including the research tools we want to keep allowed), so the tools to
deny must be enumerated explicitly, as below.

> **Note on settings.json — HUMAN-ONLY, DO NOT AUTO-APPLY**: `.claude/settings.json`
> is a blocked-write path (`02_hooks_and_permissions.md`) — no agent may edit it
> under any circumstance, including to narrow permissions. Do NOT attempt to bypass
> this by editing it directly, via Bash, or via any other tool. A human must paste
> the block below into `settings.json`'s `permissions.deny` array by hand, outside
> of any agent session.

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

## Known gotcha: `firecrawl_parse` over MCP

`firecrawl_parse` (MCP) throws unless `FIRECRAWL_API_URL` points at a self-hosted
Firecrawl instance — we only have a cloud key. **Use the CLI `firecrawl parse` skill**
for local file parsing (PDF/DOCX/etc.), not the MCP tool.

## Search credit refund

`firecrawl_search` (MCP) and `firecrawl search` (CLI) cost 2 credits per call. Calling
`firecrawl_search_feedback` with the returned result `id` refunds 1 credit (daily cap
100/team/UTC-day; stops refunding once `dailyCapReached:true`). Worth doing at high
search volume; not worth automating below that.
