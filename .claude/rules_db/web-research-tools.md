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

For everything else (scrape/search/crawl/map/interact/parse/agent/monitor), prefer the
CLI skill over the MCP tool of the same name — avoids double-counting credits and keeps
one obvious tool per job.

Pendiente humano (no aplicable por un agente): denegar los firecrawl MCP no-research en
`.claude/settings.json` → `docs/pending-human-actions.md`.

## Known gotcha: `firecrawl_parse` over MCP

`firecrawl_parse` (MCP) throws unless `FIRECRAWL_API_URL` points at a self-hosted
Firecrawl instance — we only have a cloud key. **Use the CLI `firecrawl parse` skill**
for local file parsing (PDF/DOCX/etc.), not the MCP tool.

## Search credit refund

`firecrawl_search` (MCP) and `firecrawl search` (CLI) cost 2 credits per call. Calling
`firecrawl_search_feedback` with the returned result `id` refunds 1 credit (daily cap
100/team/UTC-day; stops refunding once `dailyCapReached:true`). Worth doing at high
search volume; not worth automating below that.
