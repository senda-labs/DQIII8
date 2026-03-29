---
paths:
  - "**/*"
---
# ML Routing — 5-level automatic complexity routing

Based on `classify_task_complexity()` in `bin/orchestrator.py`.
PAL MCP server: `/tmp/pal-mcp-server/server.py` (Ollama + Groq bridge) — **available**.

## Routing Table

| Level | Trigger | Executor | Cost |
|-------|---------|----------|------|
| READ_ONLY | grep, find, ls, cat, git log/status/diff | executor-lite (Haiku) | free |
| SIMPLE_WRITE | run tests, git add/commit/push, single file edit | executor-lite (Haiku) | free |
| CODE_GEN | create function/class, new file, simple refactor | PAL → ollama/qwen2.5-coder (if available), else Sonnet | ~free |
| ARCHITECTURE | multi-file refactor, system design, planning | Sonnet (session) | paid |
| CRITICAL | production, security, deploy, credentials | Sonnet + plan-gate (Opus review) | paid |

## READ_ONLY — delegate to executor-lite (Haiku)
Triggers: grep, find, ls, list, cat, git log, git status, git diff,
  read file, count lines, how many, show, describe, explain, busca, muestra

## SIMPLE_WRITE — delegate to executor-lite (Haiku)
Triggers: pytest, run tests, git add, git commit, git push, commit, push,
  edit (single file), rename, fix typo, chmod, touch

## CODE_GEN — PAL/Ollama qwen2.5-coder (fallback: Sonnet)
Triggers: crea, create, implementa, implement, escribe, write, genera, generate,
  añade función, add function, class, refactor, simplify, extract
PAL tool: use `clink` with `cli_name: "ollama"` and `role: "coder"`
Fallback (if PAL MCP unavailable): use Sonnet directly

## ARCHITECTURE — Sonnet (session principal)
Triggers: diseña, design, architecture, plan, multi-file, sistema, migrate,
  rewrite, strategy, prompts > 500 chars
Never delegate to Haiku or Ollama for these.

## CRITICAL — Sonnet + Opus plan-gate
Triggers: production, prod, deploy, security, secret, token, credentials,
  CVE, vulnerability, exploit
Always invoke plan-gate (dqiii8-plan-gate.md) before executing.
Opus reviews the plan; proceed only after APPROVE.

## Decision algorithm (apply in order)

1. Does prompt mention production/security/deploy/credentials? → CRITICAL
2. Does prompt mention architecture/design/plan/multi-file or >500 chars? → ARCHITECTURE
3. Does prompt mention create/implement/write new code? → CODE_GEN
4. Does prompt mention tests/commit/push/single edit? → SIMPLE_WRITE
5. Otherwise (read, search, list, explain) → READ_ONLY

## PAL MCP status

```
Server: /tmp/pal-mcp-server/server.py  ✓ present
MCP config: .mcp.json → "pal" entry    ✓ configured
Ollama backend: localhost:11434         (check with: ollama ps)
```

CODE_GEN tasks route via PAL clink → ollama/qwen2.5-coder when Ollama is running.
If Ollama is down, PAL returns error → fall through to Sonnet automatically.
