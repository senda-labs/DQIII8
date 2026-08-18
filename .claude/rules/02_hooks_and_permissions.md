---
paths:
  - ".claude/hooks/**"
  - ".claude/hooks/*.py"
---
# Hooks & Permissions — DQIII8

**Order**: `pre_tool_use.py` (PermissionAnalyzer → APPROVE/DENY/ESCALATE + rules_dispatcher.py injection, ~1.432–4.469 tokens) → tool runs → `post_tool_use.py` (logs to `agent_actions`, estimates cost).
**Session**: `session_start.py` injects context+lessons; `stop.py` auto-commits + writes metrics.

| Decision | Trigger | Result |
|---|---|---|
| APPROVE | low-risk, safe path, under budget | proceeds |
| DENY | CRITICAL/HIGH_RISK pattern, blocked path, budget exceeded | **blocked, logged, final — never retry or bypass (no `--no-verify`/`--force`/reordering)** |
| ESCALATE | ambiguous risk, **or any write to the governance corpus** | blocked on the wire like DENY, but routed to the operator by `record_rejection` — resume only after the human confirms |

**Always-blocked commands**: `rm -rf /` (exact), `> /dev/sda`, `mkfs`, `dd if=`, fork bombs.
**High-risk (needs user confirmation)**: `rm -rf /anything`, `DROP TABLE`, `DELETE ... agent_actions` w/o WHERE, `DROP DATABASE`, `chmod 777 /`.

**Blocked paths — DENY on write, absolute, no carve-outs, source of truth = `BLOCKED_PATHS` in `permission_analyzer.py`:**
`CLAUDE.md`, `.env`, `secrets`, `dqiii8.db`, `.claude/settings.json`, `schema_v2.sql`, `.git/`, `id_rsa`, `id_ed25519`, `.ssh/`, `context/proposito.md`, `.claude/settings.local.json`.
No exception for "user asked for it" — the code has none. A human edits these directly, outside any agent session. (Other docs, e.g. `dqiii8-ops.md`, must not restate this list — link here instead, to avoid drift.)

**Governance paths — ESCALATE on write, source of truth = `GOVERNANCE_PATHS` in `permission_analyzer.py`:**
`.claude/hooks/`, `.claude/rules/`, `.claude/rules_db/`, `.claude/agents/`, `.claude/skills/`, `.claude/settings.local.json`.
This is the corpus that *defines* the rules every other check enforces, so a write here is never routine — but a hard DENY would make the governance system unmaintainable by any agent (including the remediation work that added this control), so the verdict is ESCALATE: blocked pending explicit human confirmation. `.claude/settings.local.json` appears in both lists; **GOVERNANCE wins for that one path only** — it is the file whose MCP allow-list created the bypass this control closes, so it must stay human-editable-with-confirmation rather than permanently frozen. Everywhere else the two lists disagree, **DENY wins** (e.g. `.claude/rules/secrets.md` denies on `secrets`). Not waived by `DQIII8_MODE=autonomous` and not reachable by `learned_approvals`: the check runs at step 3, ahead of both.

**Tools covered by the path checks (v3.5)** — the check used to run only for `Edit`/`Write`/`MultiEdit` plus a Bash heuristic, which left the MCP tools that `settings.local.json` allow-lists writing to blocked files unchecked. `_candidate_paths(tool, tool_input)` now extracts every path a call could touch, and the same BLOCKED/GOVERNANCE match runs against all of them:

| Tool | Paths extracted |
|---|---|
| `Edit` / `Write` / `MultiEdit` | `file_path` |
| `mcp__filesystem__*` (write-capable) | `path`, `file_path`, `source`, `destination`, `target`, `dest` — read-only tools (`read_text_file`, `directory_tree`, `search_files`, …) are exempt; anything else under `mcp__filesystem__` fails **closed** into the check, since `settings.json` allows the whole `mcp__*` glob |
| `mcp__dqiii8-db__execute` / any MCP tool taking `sql`/`query`/`statement` | `ATTACH DATABASE '<path>'`, `VACUUM INTO '<path>'`, plus any path-shaped string literal (best-effort regex, not a SQL parser) |
| `Bash` | unchanged token/write-operator heuristic in `_bash_touches_blocked()`, now also escalating on governance paths |

**Web egress gate (v3.4)** — `WebFetch`, `WebSearch` and any `mcp__*` tool carrying a `url`. There is deliberately **no host allowlist**: real usage spans 211 distinct hosts, 125 fetched exactly once, so an allowlist would block the research this system exists to do. The gate targets exfiltration *shape* instead. DENY: non-http(s) scheme, `user:pass@host` userinfo, recognised secret shapes in the URL/query (API keys, Telegram bot token, PEM block), request-capture sinks (webhook.site, ngrok, pipedream, oast…), cloud-metadata addresses. ESCALATE: private/loopback/obfuscated-IP hosts, opaque ≥40-char encoded tokens. WebFetch's `prompt` is not gated — it is applied to fetched content locally and never leaves the VPS. Runs at step 3e, before `learned_approvals`, so a repeated exfil URL cannot be auto-whitelisted.

**Rules dispatcher**: maps tool+input → 1-3 rule aliases from `.claude/rules_db/` (~1.432-4.469 tokens, medido 2026-08-17 con `token_estimate()`
sobre la matriz de `tests/test_rules_dispatcher.py`; el suelo de 1.432 es `ops` + `core-behavior`,
siempre inyectados; el techo de 4.469 es Bash con keyword `agent|orchestrat`); never loads all files.
El rango es canónico en el docstring de `rules_dispatcher.py` y debe re-medirse cuando cambie
el tamaño de un fichero `_ALWAYS`/muy disparado o se añada un trigger.

**Before editing anything in `.claude/hooks/`**: check which DB tables it writes (`agent_actions`/`session_events`) → confirm APPROVE/DENY/ESCALATE contract unchanged → dry-run (`echo '{"tool_name":"Bash","tool_input":{"command":"ls"}}' | python3 .claude/hooks/pre_tool_use.py`) → hook errors must silently degrade to APPROVE, never block startup.
