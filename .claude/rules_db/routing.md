---
paths:
  - "**/*"
---
# Task Routing — 5-level complexity + Haiku-first delegation

## Routing Table

| Level | Trigger keywords | Executor | Cost |
|-------|-----------------|----------|------|
| READ_ONLY | grep, find, ls, cat, git log/status/diff, read, count, show, describe | executor-lite (Haiku) | free |
| SIMPLE_WRITE | pytest, run tests, git add/commit/push, single-file edit, rename, fix typo | executor-lite (Haiku) | free |
| CODE_GEN | create, implement, write new code, class, function, refactor, extract | PAL → ollama/qwen2.5-coder, fallback Sonnet | ~free |
| ARCHITECTURE | design, plan, multi-file, system, migrate, rewrite, strategy, >500-char prompt | Sonnet (session) | paid |
| CRITICAL | production, security, deploy, credentials, CVE, exploit | Sonnet + Opus plan-gate | paid |

## Decision algorithm (apply in order)
1. production/security/deploy/credentials? → CRITICAL
2. architecture/design/plan/multi-file or >500 chars? → ARCHITECTURE
3. create/implement/write new code? → CODE_GEN
4. tests/commit/push/single edit? → SIMPLE_WRITE
5. otherwise → READ_ONLY

## Delegation rules

**executor-lite (Haiku)** — READ_ONLY + SIMPLE_WRITE:
pytest, git ops, ls/grep/find, read single file, count lines, simple edits

**explorer-lite (Haiku)** — READ_ONLY codebase variant:
finding functions/classes, reading docs, "where is X defined?"

**PAL/Ollama** — CODE_GEN:
`clink` with `cli_name: "ollama"`, `role: "coder"`. If Ollama down → Sonnet.

**Sonnet (session)** — ARCHITECTURE + CRITICAL only.
Goal: Haiku handles 70%+ of operations. Reserve Sonnet for reasoning.

## PAL MCP status
```
Server: /tmp/pal-mcp-server/server.py   — EPHEMERAL (/tmp): absent after reboot.
                                          Verified ABSENT 2026-07-05. Check before use:
                                          test -f /tmp/pal-mcp-server/server.py
Ollama backend: localhost:11434          ✓ up 2026-07-05 (qwen2.5-coder:7b + bge-m3)
                                          check: curl -s localhost:11434/api/tags
```
If the PAL server is absent, CODE_GEN falls through to direct Ollama or Sonnet — do not
assume `clink`/PAL is available without the check above.
