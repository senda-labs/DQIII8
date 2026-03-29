---
paths:
  - "**/*"
---
# Token Routing — Haiku-first policy

See `ml-routing.md` for the full 5-level routing table.
This file defines the delegation rules for subagents.

## Delegate to executor-lite (Haiku)
Complexity levels: READ_ONLY and SIMPLE_WRITE

ALWAYS use executor-lite for:
- Running tests (`pytest`, `python3 -m pytest`, etc.)
- Listing files, counting lines, directory exploration
- Git operations (add, commit, push, status, diff, log)
- Reading individual files
- Grep/search operations
- Simple single-file edits (typo fixes, constant changes)
- Running scripts and reporting output

## Delegate to explorer-lite (Haiku)
Complexity level: READ_ONLY (codebase search variant)

ALWAYS use explorer-lite for:
- Codebase exploration (finding functions, classes, patterns)
- Reading documentation files
- Understanding code structure before a refactor
- Answering "where is X defined?" questions

## CODE_GEN — PAL/Ollama or Sonnet
Complexity level: CODE_GEN

Prefer: delegate via PAL MCP clink → ollama/qwen2.5-coder
Fallback: use Sonnet (current session) if PAL unavailable

## Keep in Sonnet (current context)
Complexity levels: ARCHITECTURE and CRITICAL

ONLY use Sonnet for:
- Planning and architecture decisions
- Complex multi-file refactors
- Debugging subtle or non-obvious bugs
- Writing new features from scratch
- Evaluating trade-offs between approaches
- Critical/production/security tasks (with plan-gate)

## Goal
Use Haiku for 70%+ of tool operations. Reserve Sonnet for reasoning.
Every time you are about to run a test, list files, do a grep, or make a
trivial edit — stop and delegate to executor-lite instead.
