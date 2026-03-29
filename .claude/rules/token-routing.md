---
paths:
  - "**/*"
---
# Token Routing — Haiku-first policy

## Delegate to executor-lite (Haiku)
ALWAYS use executor-lite for:
- Running tests (`pytest`, `python3 -m pytest`, etc.)
- Listing files, counting lines, directory exploration
- Git operations (add, commit, push, status, diff, log)
- Reading individual files
- Grep/search operations
- Simple single-file edits (typo fixes, constant changes)
- Running scripts and reporting output

## Delegate to explorer-lite (Haiku)
ALWAYS use explorer-lite for:
- Codebase exploration (finding functions, classes, patterns)
- Reading documentation files
- Understanding code structure before a refactor
- Answering "where is X defined?" questions

## Keep in Sonnet (current context)
ONLY use Sonnet for:
- Planning and architecture decisions
- Complex multi-file refactors
- Debugging subtle or non-obvious bugs
- Writing new features from scratch
- Evaluating trade-offs between approaches
- Tasks that require understanding the full system context

## Goal
Use Haiku for 70%+ of tool operations. Reserve Sonnet for reasoning.
Every time you are about to run a test, list files, do a grep, or make a
trivial edit — stop and delegate to executor-lite instead.
