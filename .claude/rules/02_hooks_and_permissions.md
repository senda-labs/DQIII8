---
paths:
  - ".claude/hooks/**"
  - ".claude/hooks/*.py"
---
# Hooks & Permissions — DQIII8

**Order**: `pre_tool_use.py` (PermissionAnalyzer → APPROVE/DENY/ESCALATE + rules_dispatcher.py injection) → tool runs → `post_tool_use.py` (logs to `agent_actions`, estimates cost).
**Session**: `session_start.py` injects context+lessons; `stop.py` auto-commits + writes metrics.
**PermissionRequest**: `permission_request.py` — separate from PermissionAnalyzer, wired to the `PermissionRequest` hook event. If `DQIII8_MODE != "autonomous"` → always allow. In autonomous mode: a hit in `permission_request.py`'s **own** `CRITICAL_PATTERNS` (a different constant from the analyzer's same-named list — plain substrings) → Telegram escalation, 10-min timeout → automatic deny; anything else → allow. It only fires for tools *absent* from `.claude/settings.json`'s `permissions.allow`, which pre-approves `Bash`, the other core tools and the whole `mcp__*` glob — so almost nothing reaches this layer. Force-push is no longer among the gaps this left: as of 2026-08-18 `HIGH_RISK_PATTERNS` in `permission_analyzer.py` DENIES it directly, on every Bash call (see `git-safety.md`). It is **not** a substitute for PermissionAnalyzer, which runs on every call regardless.

| Decision | Trigger | Result |
|---|---|---|
| APPROVE | low-risk, safe path, under budget | proceeds |
| DENY | CRITICAL/HIGH_RISK pattern, blocked path, budget exceeded | **blocked, logged, final — never retry or bypass (no `--no-verify`/`--force`/reordering)** |
| ESCALATE | ambiguous risk, **or any write to the governance corpus** | blocked on the wire like DENY, but routed to the operator by `record_rejection` — resume only after the human confirms |

`learned_approvals` runs **last**, after every check below: a historically-approved pattern can never soften a DENY or ESCALATE, and none of these checks is waived by `DQIII8_MODE=autonomous`.

**Blocked commands (DENY)** — matched flag-order/style agnostically, not as literal strings; matchers are `_rm_destructive_targets()`, `CRITICAL_PATTERNS` and `HIGH_RISK_PATTERNS` in `permission_analyzer.py` (that module's `CRITICAL_PATTERNS`, not `permission_request.py`'s unrelated list of the same name): `rm -rf /` and any non-root target/flag-order variant, `> /dev/sda`-class disk devices, `mkfs`, `dd` to a disk device, fork bombs, `chmod 777 /` (incl. `-R`/`a+rwx`), disk-scrubbing tools (`wipefs`/`parted`/`shred`/… on `/dev/*`) and `tee` into a device, `DROP TABLE`/`DROP DATABASE`/`DROP TRIGGER` (the triggers are what make the audit tables append-only), `PRAGMA writable_schema`, an unbounded `DELETE FROM` an audit table (no `WHERE`, or a tautological one — `WHERE 1=1`/`TRUE`/`1`, plus the semantic no-ops `IS NOT NULL`/`> -1`/`<> -1` and always-true literal comparisons like `2>1`; shape-matching, not a SQL parser — see the CEILING comment on `_SQL_TAUTOLOGY` for what it still misses), `git push --force`/`-f`/`--force-with-lease` (any flag order/remote), and *any* `UPDATE`/`ALTER TABLE`/`TRUNCATE`/`REPLACE INTO`/`INSERT INTO` against `learned_approvals`/`permission_decisions`/`agent_actions`/`instincts`/`sqlite_master`/`sqlite_schema` regardless of predicate (the `DELETE` guard also covers `session_memory`). A `<schema>.` qualifier does not evade the table match. Scanned in a Bash command, in an MCP tool's `sql`/`query`/`statement` argument (e.g. `mcp__dqiii8-db__execute`), and in `mcp__context-mode__ctx_execute*` code — same verdict through any of them.

**The one carve-out; SSOT = `ALLOWED_DELETIONS` in `permission_analyzer.py`:** so "always" does *not* hold for `rm`. `_rm_target_is_allowed()` gates both the recursive-force `rm` DENY and the whole `HIGH_RISK_PATTERNS` branch (the `CRITICAL_PATTERNS` disk-device/fork-bomb branch has no carve-out at all): the command is approved when **every** `rm` target's final path component is an allowed-deletion name — `node_modules`, `dist`, `build`, `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `tmp`, `/tmp/`, `*.pyc`, `plugins/cache/`. All-or-nothing: one non-matching target and the whole command is denied. Match is on the *final path component* (`node_modules_backup` is not exempt) and an absolute target must also resolve inside `SAFE_PROJECT_DIRS` (`rm -rf /etc/dist` still denies). Rationale: these are regenerable build/cache artifacts, so cache cleanup is not data loss and needs no human round-trip. `DENIAL_HINTS` surfaces the constant at denial time; no other doc restates the list.

**Blocked paths — DENY on write, absolute, no carve-outs; SSOT = `BLOCKED_PATHS` in `permission_analyzer.py`:**
`CLAUDE.md`, `.env`, `secrets`, `dqiii8.db`, `.claude/settings.json`, `schema_v2.sql`, `.git/`, `id_rsa`, `id_ed25519`, `.ssh/`, `context/proposito.md`, `.claude/settings.local.json`.
No exception for "user asked for it" — the code has none. A human edits these directly, outside any agent session. (Other docs, e.g. `dqiii8-ops.md`, must not restate this list — link here instead, to avoid drift.)

**Governance paths — ESCALATE on write; SSOT = `GOVERNANCE_PATHS` in `permission_analyzer.py`:**
`.claude/hooks/`, `.claude/rules/`, `.claude/rules_db/`, `.claude/agents/`, `.claude/skills/`, `.claude/settings.local.json`.
This corpus *defines* the rules every other check enforces, so a write here is never routine — but a hard DENY would make the governance system unmaintainable, hence ESCALATE. `.claude/settings.local.json` is in both lists; **GOVERNANCE wins for that one path only** (it must stay human-editable-with-confirmation, not frozen). Everywhere else the two lists disagree, **DENY wins**.

**Tools covered by the path checks** — `_candidate_paths()` extracts every path a call could touch; the same BLOCKED/GOVERNANCE match runs against all of them:

| Tool | Paths extracted |
|---|---|
| `Edit`/`Write`/`MultiEdit`/`NotebookEdit`/`Artifact` | `file_path` (`notebook_path` for `NotebookEdit`) |
| `mcp__filesystem__*` write-capable, and `mcp__github__*` write-shaped (any suffix that is not `get_`/`list_`/`search_`) | `path`, `file_path`, `source`, `destination`, `target`, `dest`, `paths`, `file_paths`, plus `files[].path` (`push_files`); unrecognised keys fail **closed** |
| `mcp__filesystem__*` read-only (`read_text_file`, `directory_tree`, `search_files`, …) | not path-blocked, but still credential-gated — a "read-only" tool reading `.env`/`id_rsa` is still a credential leak and is denied |
| any MCP tool taking `sql`/`query`/`statement` | path-shaped literals (`ATTACH DATABASE`, `VACUUM INTO`; best-effort regex, not a SQL parser) |
| `mcp__context-mode__ctx_execute` / `ctx_execute_file` / `ctx_batch_execute` | Bash-equivalent: its `code`/`path`/`commands[].command` text runs through the same blocked-path and command checks (this server is allow-listed and its own tool descriptions steer callers away from Bash) |
| any other unrecognised `mcp__*` tool | catch-all: the full JSON payload is scanned for secret-shaped strings, so a tool with no `url`/`query`/path key can't smuggle a credential out unexamined |
| `Bash` | token/write-operator heuristic, cwd-aware (a leading `cd <dir> &&`/`;` prefix is resolved before relative write targets) and glob-aware, not literal substrings. "Write" is not only `>`/`>>`: `cp`/`mv`/`rsync`/`install`/`ln`/`dd`, in-place editors (`sed -i`, `perl -i`, `ed`), archive extraction, `patch`/`git apply`/`git checkout -- <path>`, DB clients running DML, and inline Python/Perl (`open(…,'w')`, `write_text`, `shutil.*`, `os.remove/rename`, `subprocess.*`) all count |

**Web egress gate** — `WebFetch`, `WebSearch`, any `mcp__*` tool carrying `url`/`query`/`urls`, and egress inside Bash (not just curl/wget: also `nc`/`socat`/`scp`/`rsync`/`ssh` and Python `urllib`/`requests`/`httpx`/`socket`). Deliberately **no host allowlist** (research spans 200+ hosts) — it targets exfiltration *shape*. DENY: non-http(s) scheme, `user:pass@host` userinfo, secret-shaped values in URL/query, request-capture sinks (webhook.site, ngrok, pipedream, oast…), cloud-metadata addresses. ESCALATE: private/loopback/obfuscated-IP hosts, opaque ≥40-char tokens. WebFetch's `prompt` is not gated (applied locally to fetched content).

**Rules dispatcher**: maps tool+input → 1-3 rule aliases from `.claude/rules_db/`; never loads all files. The canonical token range, and the rule for re-measuring it, live in `rules_dispatcher.py`'s docstring (enforced by `tests/test_rules_dispatcher.py` and `bin/tools/validate_rules_registry.py`) — never restate the numbers here. This file's own size counts toward that ceiling: keep additions terse and point at code rather than narrating it.

**Before editing anything in `.claude/hooks/`**: check which DB tables it writes (`agent_actions` — `session_events` does not exist, see `01_database_mutations.md`) → confirm the APPROVE/DENY/ESCALATE contract is unchanged → dry-run (`echo '{"tool_name":"Bash","tool_input":{"command":"ls"}}' | python3 .claude/hooks/pre_tool_use.py`) → hook errors must silently degrade to APPROVE, never block startup.
