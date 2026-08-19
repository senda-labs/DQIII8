# Tool Lanes — claude / cc / dispatch (DQIII8)

Referenced by `rules_dispatcher.py` alias `tools` (injected when a Bash command
mentions `claude` or `cc`).

## One lane per job
- **Interactive orchestration** → this CC session (Sonnet). Delegate with the Agent tool or
  `claude -p`. The `openrouter_wrapper.py` NIM/Groq lane is **dormant — do not invoke it**
  (REGLA NIM, `.claude/rules/00_core_behavior.md`); routing SSOT is
  `.claude/rules/03_tiering_and_routing.md`, history in
  `.claude/rules_db/archive/multi-tier-dormant-2026-08.md`.
- **Fire-and-forget agent task** → `/dispatch-agent` skill. Both sync and async
  usable (see dqiii8-error-prevention.md §Dispatch).
- **Long batch jobs** (intl-reports generate, stress tests) → external tmux, never
  inline in the session. `claude -p` non-interactive cannot spawn subagents (the Agent tool
  exists only in interactive CC sessions) — so a batch job must be shaped as one linear task,
  not as an orchestrator that fans out. Its historical fallback to `AGENT_ROUTING` is dormant
  with the rest of the wrapper (scope note archived in
  `.claude/rules_db/archive/multi-tier-dormant-2026-08.md`).
- **Web content** → `mcp__fetch` first ($0), firecrawl CLI on failure
  (web-research-tools.md). CDP investigation → `/cdp-investigate` skill, port 9333,
  read-only, verify tunnel with curl before assuming up.

## claude CLI safety
- `claude -p` runs headless: hook failures degrade to APPROVE; do not rely on
  interactive ESCALATE prompts existing there.
