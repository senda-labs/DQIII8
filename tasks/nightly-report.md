nohup: ignoring input
# DQ Nightly Report — 2026-03-19 04:24 UTC

## 1. Auto-learner consolidation
[auto-learner] consolidate: 5 lecciones sistémicas añadidas
✓ Auto-learner completed

## 2. Knowledge indexing
  Indexing formal_sciences... [WARN] No indexable .md files found in /root/jarvis/knowledge/formal_sciences
✓
  Indexing natural_sciences... [WARN] No indexable .md files found in /root/jarvis/knowledge/natural_sciences
✓
  Indexing social_sciences... [INDEXER] domain=social_sciences: 1 file(s) to index
  finance/risk_management_intro.md
    7 chunk(s)
    chunk 0:  117 chars |   456ms
    chunk 1:  467 chars |   455ms
    chunk 2:  683 chars |   444ms
    chunk 3:  363 chars |   403ms
    chunk 4:  341 chars |   242ms
    chunk 5:  254 chars |   262ms
    chunk 6:  255 chars |   201ms

[OK] domain=social_sciences: 7 chunks → /root/jarvis/knowledge/social_sciences/index.json (144 KB)
✓
  Indexing humanities_arts... [INDEXER] domain=humanities_arts: 1 file(s) to index
  literature/narrative_basics.md
    5 chunk(s)
    chunk 0:  116 chars |   128ms
    chunk 1:  799 chars |   615ms
    chunk 2:  541 chars |   459ms
    chunk 3:  476 chars |   425ms
    chunk 4:  589 chars |   519ms

[OK] domain=humanities_arts: 5 chunks → /root/jarvis/knowledge/humanities_arts/index.json (103 KB)
✓
  Indexing applied_sciences... [INDEXER] domain=applied_sciences: 1 file(s) to index
  software_engineering/architecture_overview.md
    5 chunk(s)
    chunk 0:  133 chars |   131ms
    chunk 1: 1007 chars |   764ms
    chunk 2:  624 chars |   425ms
    chunk 3:  802 chars |   593ms
    chunk 4:  244 chars |   187ms

[OK] domain=applied_sciences: 5 chunks → /root/jarvis/knowledge/applied_sciences/index.json (104 KB)
✓

## 3. Domain classifier tests
  Test 1: "calculate portfolio VaR at 95%"
domain=natural_sciences score=0.4533 method=embedding

  Test 2: "write chapter 5 where Lin Feng finds the artifact"
domain=humanities_arts score=1.0000 method=keyword

  Test 3: "refactor the DatabaseManager class"
domain=natural_sciences score=0.5251 method=embedding

## 4. Unresolved errors
72|AgentError|Agent type 'auditor' not found. Available agents: general-purpose, statusline-setup, Explore, Plan, claude-code-guide, superpowers:code-reviewer, feature-dev:code-architect, feature-dev:code-explorer, feature-dev:code-reviewer, pr-review-toolkit:code-reviewer, pr-review-toolkit:code-simplifier, pr-review-toolkit:pr-test-analyzer, pr-review-toolkit:silent-failure-hunter, pr-review-toolkit:comment-analyzer, pr-review-toolkit:type-design-analyzer, hookify:conversation-analyzer, episodic-memory:sear
73|BashError|Exit code 1
The following paths are ignored by one of your .gitignore files:
database/audit_reports/audit-2026-03-19-04.md
hint: Use -f if you really want to add them.
hint: Turn this message off by running
hint: "git config advice.addIgnoredFile false"
74|mcp__sqlite__executeError|MCP error -32000: no such column: resolution_note
75|mcp__sqlite__executeError|MCP error -32000: no such column: resolution_note
76|mcp__sqlite__executeError|MCP error -32000: no such column: resolution_note
77|mcp__sqlite__executeError|MCP error -32000: no such column: resolution_note
78|mcp__sqlite__executeError|MCP error -32000: no such column: resolution_note
79|mcp__sqlite__executeError|MCP error -32000: no such column: resolution_note
80|mcp__sqlite__executeError|MCP error -32000: no such column: resolution_note
81|AgentError|Agent type 'auditor' not found. Available agents: general-purpose, statusline-setup, Explore, Plan, claude-code-guide, superpowers:code-reviewer, feature-dev:code-architect, feature-dev:code-explorer, feature-dev:code-reviewer, pr-review-toolkit:code-reviewer, pr-review-toolkit:code-simplifier, pr-review-toolkit:pr-test-analyzer, pr-review-toolkit:silent-failure-hunter, pr-review-toolkit:comment-analyzer, pr-review-toolkit:type-design-analyzer, hookify:conversation-analyzer, episodic-memory:sear
82|BashError|Exit code 1
The following paths are ignored by one of your .gitignore files:
database/audit_reports/audit-2026-03-19-04.md
hint: Use -f if you really want to add them.
hint: Turn this message off by running
hint: "git config advice.addIgnoredFile false"

## 5. System health
  Disk: 50G free (49% used)
  RAM: 6235MB available
  DB size: 5.2M
  Uptime: up 1 week, 1 day, 8 hours, 14 minutes

## 6. Git status
