# Tool Lanes — claude / cc / dispatch (DQIII8)

Referenced by `rules_dispatcher.py` alias `tools` (injected when a Bash command
mentions `claude` or `cc`). Created 2026-07-05 (Fable 5 audit) — alias previously
pointed at a missing file.

## One lane per job
- **Interactive orchestration** → this CC session (Sonnet). Subagents via Agent tool
  consume Anthropic tokens — for NIM/Groq work use the wrapper instead:
  `python3 /root/dqiii8/bin/core/openrouter_wrapper.py --agent <agente> --no-enrich "<prompt>"`
- **Fire-and-forget agent task** → `/dispatch-agent` skill. Async mode fixed 2026-07-05,
  both sync and async usable (see dqiii8-error-prevention.md §Dispatch).
- **Long batch jobs** (intl-reports generate, stress tests) → external tmux, never
  inline in the session. `claude -p` non-interactive cannot spawn subagents — routing
  falls to `AGENT_ROUTING` in the wrapper (03_tiering §scope note).
- **Web content** → `mcp__fetch` first ($0), firecrawl CLI on failure
  (web-research-tools.md). CDP investigation → `/cdp-investigate` skill, port 9333,
  read-only, verify tunnel with curl before assuming up.

## claude CLI safety
- Never export/modify `ANTHROPIC_API_KEY` in production (OAuth only).
- `claude -p` runs headless: hook failures degrade to APPROVE; do not rely on
  interactive ESCALATE prompts existing there.
