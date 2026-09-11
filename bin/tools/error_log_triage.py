#!/usr/bin/env python3
"""Mark already-understood error_log categories as resolved.

Root-cause fix for the 2026-08-21 disaster-scenario sweep's "89 unresolved
error_log rows, no process ever closes the loop" finding: error_log grows
without bound because nothing ever revisits a row once its cause is
understood and accepted. This script is the reusable, idempotent mechanism
for that -- not a one-off UPDATE -- so the next already-explained category
(e.g. a future documented directive change) has a place to register a
pattern instead of silently accumulating in the backlog again.

Deliberately conservative: only resolves rows matching a hand-reviewed
pattern tied to a specific, cited, standing decision -- never a blanket
"mark everything resolved" pass. Run manually; not wired into any hook.
"""

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "dqiii8.db"

# Each entry: (error_type, message LIKE pattern, resolution note, citation)
KNOWN_EXPLAINED = [
    (
        "openrouter_wrapperError",
        "nim/%",
        "Expected under REGLA NIM Anthropic-only directive (2026-08-18): "
        "non-Anthropic providers non-operational since NIM 403 on 2026-08-16.",
        ".claude/rules/00_core_behavior.md #REGLA NIM",
    ),
    (
        "openrouter_wrapperError",
        "openrouter/%",
        "Expected under REGLA NIM Anthropic-only directive (2026-08-18): "
        "non-Anthropic providers non-operational since NIM 403 on 2026-08-16.",
        ".claude/rules/00_core_behavior.md #REGLA NIM",
    ),
    # 2026-08-21: individually reviewed all 69 rows unresolved at the time
    # (see git log for this file). Each pattern below is a distinct root
    # cause, not a blanket sweep -- rows with no stored detail beyond an
    # exit code, or with only a partial/ambiguous message, were left
    # unresolved rather than guessed at.
    (
        "ReadError",
        "File content (%) exceeds maximum allowed tokens%",
        "Expected: Read tool's own token-limit guard, working as designed "
        "(the message itself instructs using offset/limit). Not a defect.",
        "Read tool built-in behavior",
    ),
    (
        "ReadError",
        "EISDIR: illegal operation on a directory%",
        "Expected: Read was called on a directory path, not a file. "
        "Correct failure mode, not a defect.",
        "Node fs EISDIR semantics",
    ),
    (
        "ReadError",
        "File does not exist. Note: your current working directory%",
        "Expected: Read attempted on a path that does not exist during "
        "normal exploration. Not a defect.",
        "Read tool built-in behavior",
    ),
    (
        "BashError",
        "%ignored by one of your .gitignore files%",
        "Not an error: git correctly refused to add gitignored-only paths "
        "and exited nonzero to signal it. Matches the documented "
        "gitignore-respecting `git add` protocol.",
        ".claude/rules_db/git-safety.md #Git add protocol",
    ),
    (
        "BashError",
        "%alias: dqa: not found%",
        "Documented gotcha: aliases are not available in non-interactive "
        "Bash. Use the full sqlite3 path instead of the `dqa` alias.",
        ".claude/rules_db/git-safety.md #Bash rules",
    ),
    (
        "BashError",
        "%database/schema.sql: No such file or directory%",
        "Expected: database/schema.sql was renamed/removed; "
        "database/schema_v2.sql is the sole schema SSOT.",
        "CLAUDE.md #Exigencias no negociables",
    ),
    (
        "BashError",
        "%bun: command not found%",
        "Environment gap since fixed -- bun is installed and resolvable "
        "on PATH as of this triage run (verified with `which bun`).",
        "verified 2026-08-21",
    ),
    (
        "BashError",
        "%veredictos cambiados%",
        "Expected: Fase A stress-test harness output (permission_analyzer.py "
        "corpus regression runs), nonzero exit is the harness's own "
        "review-me signal, not an application bug.",
        "git log Fase A commits (A3a-A7), 2026-08-20/21",
    ),
    (
        "BashError",
        "%FP sin corregir%adversariales%",
        "Expected: same Fase A stress-test harness, false-positive-tracking "
        "report variant. Nonzero exit is the harness's review-me signal, "
        "not an application bug -- the FPs it lists were fixed by "
        "subsequent Fase A commits.",
        "git log Fase A commits (A3a-A7), 2026-08-20/21",
    ),
    (
        "BashError",
        "%SELECT ts, score FROM audit_reports%",
        "One-off ad-hoc scratch query typo (audit_reports has no `ts`/`score` "
        "columns -- real columns are `timestamp`/`overall_score`). No "
        "production script uses this query (grep-verified); scratch-only.",
        "verified 2026-08-21 via .schema audit_reports + grep",
    ),
    (
        "BashError",
        "%HEALTH SCORE:%WARNING%",
        "Expected: /audit exits nonzero on a WARNING-tier health score by "
        "design, to make the report visible. The underlying low "
        "error-resolution-rate finding is what this triage run addresses.",
        ".claude/skills/audit/SKILL.md #Score interpretation",
    ),
    (
        "BashError",
        "%dict%object has no attribute%decision%",
        "One-off ad-hoc scratch script bug (used r.decision instead of "
        "r['decision'] on a dict). No production code affected.",
        "scratch-only, 2026-08-21 disaster-scenario testing",
    ),
    (
        "BashError",
        "%no such module: vec0%",
        "One-off ad-hoc scratch script omitted loading the sqlite-vec "
        "extension before querying a vec0 virtual table. No production "
        "code affected.",
        "scratch-only, 2026-08-21 DB investigation",
    ),
    (
        "BashError",
        "%unexpected token `&%",
        "One-off scratch command bug: an unquoted `&` inside a real "
        "project directory name (m&a-assignment) broke bash's for-loop "
        "list parsing. No production code affected.",
        "scratch-only, 2026-08-21 orphan-project audit",
    ),
    (
        "BashError",
        "%cites `scripts/save_response.py`%",
        "Cause identified and fixed: the stale citation this pre-commit "
        "warning flagged was corrected in intl-reports-ops.md.",
        "commit b618d6d, 2026-08-21",
    ),
    (
        "ScheduleWakeupError",
        "%prompt` is required when%stop%",
        "One-off tool-call mistake: ScheduleWakeup called without `prompt` "
        "while not stopping. Self-correcting -- no downstream effect.",
        "scratch-only, 2026-08-21 background-work call",
    ),
    (
        "mcp__dqiii8-db__executeError",
        "%SQL too long%",
        "Expected: MCP server enforces a 1000-char SQL length cap. Not a "
        "defect -- the caller should chunk or simplify the statement.",
        "MCP server built-in limit",
    ),
    (
        "mcp__dqiii8-db__queryError",
        "%no such column: summary%",
        "Documented gotcha: error_log has no `summary` column. Already "
        "codified as a known pitfall.",
        ".claude/rules/01_database_mutations.md #error_log",
    ),
    (
        "mcp__filesystem__write_fileError",
        "%Access denied - path outside allowed directories%",
        "Expected: filesystem MCP server correctly enforced its sandbox "
        "boundary. Security control working as designed, not a defect.",
        "mcp__filesystem__* sandbox enforcement",
    ),
]

# 2026-08-21: rows whose stored error_message is only a bare "Exit code N"
# (or a generic "Command timed out") carry no distinguishing text a LIKE
# pattern can match on. For those, the only way to find a cause is to cross-
# reference agent_actions.action_id (or, if that's unset, the session's own
# JSONL transcript by timestamp -- both were used here). Each entry below
# is a single row, resolved by id because the recovered command is a one-
# off, not a recurring category.
EXPLICIT_IDS = [
    (
        1696,
        "Recovered command (agent_actions id 424): "
        "`systemctl restart dqiii8-bot && sleep 4 && systemctl is-active "
        "dqiii8-bot`, exit 144. Likely transient: 4s was not always enough "
        "for the restart to reach 'active'. Service verified healthy and "
        "active today (2026-08-21).",
        "agent_actions.id=424; verified via systemctl is-active",
    ),
    (
        1706,
        "Recovered command (agent_actions id 481): "
        "`ls ~/.claude/hooks/ 2>/dev/null`, exit 2. ~/.claude is the global "
        "Claude config dir, not the project's .claude/hooks/ under "
        "/root/dqiii8 -- a one-off path mixup, not a defect.",
        "agent_actions.id=481",
    ),
    (
        3542,
        "Duplicate log entry (no action_id) for the same command as id "
        "3544, confirmed via the session's own transcript: parallel/twin "
        "logging of one Fase A dev script, not a distinct failure.",
        "session 61743d5f transcript, 2026-08-20T23:54:58Z",
    ),
    (
        3543,
        "Duplicate log entry (no action_id) for the same command as id "
        "3545, confirmed via the session's own transcript: parallel/twin "
        "logging of one Fase A dev command, not a distinct failure.",
        "session 61743d5f transcript, 2026-08-21T00:05:48Z",
    ),
    (
        3544,
        "Recovered command (agent_actions id 5676): a Fase A stress-test "
        "harness dev step building a6_live_probe.py from a5_live_probe.py "
        "via sed, then printing it. Scratch dev command from that day's "
        "permission_analyzer.py work, not a persisted defect.",
        "agent_actions.id=5676; git log Fase A commits",
    ),
    (
        3545,
        "Recovered command (agent_actions id 5683): "
        '`pkill -f "grep -qE .passed" ; python3 bin/tools/'
        "validate_rules_registry.py | tail -4`, a Fase A dev-session "
        "housekeeping step (killing a stray background grep, then "
        "checking the validator). Scratch dev command, not a defect.",
        "agent_actions.id=5683",
    ),
    (
        3574,
        "No action_id and no exact-timestamp Bash tool_use in this "
        "session's transcript, but the surrounding window "
        "(12:09:40-12:10:08) is fully accounted for by the dqiii8_knowledge.db "
        "table/view investigation that led to the 2026-08-21 orphan-table "
        "purge (docs/ARCHITECTURE.md) -- one of that cluster's commands "
        "(a recursive grep across bin/ and .claude/, or a DB heredoc) hit "
        "the 2-minute timeout. The investigation itself completed via the "
        "other commands in the same window.",
        "session 5dcae8a4 transcript, 2026-08-21T12:09:40-12:10:08Z",
    ),
    (
        3589,
        "Duplicate log entry (no action_id) for the same command as id "
        "3590, same exit code (123) and same timestamp region: parallel/"
        "twin logging of one general-purpose subagent's find|xargs|grep "
        "command, not a distinct failure.",
        "agent_actions.id=6457 (id 3590's linked action)",
    ),
    (
        3590,
        "Recovered command (agent_actions id 6457): "
        '`find ... -name "*.service" -o -name "*.timer" | xargs grep -l '
        '"ulimit\\|MemoryLimit\\|CPUQuota"`, exit 123. Expected xargs '
        "semantics: exits 123 when some (not all) grep invocations find no "
        "match, which is normal when searching many files for one pattern.",
        "agent_actions.id=6457; xargs(1) exit-status semantics",
    ),
    (
        1686,
        "Recovered command (agent_actions id 264): "
        '`sqlite3 .../dqiii8.db "SELECT COUNT(*) as total_actions, '
        'SUM(CASE WHEN success=1 THEN 1 ELSE 0 E..."` (text truncated at '
        "agent_actions.file_path's 120-char storage limit; error_log's own "
        "error_message field for this row holds only 'Exit code 1', no "
        "SQL error text). A one-off ad-hoc health-check query from that "
        "day's stress testing; no evidence it affected production code, "
        "but the exact clause that failed can't be confirmed past the "
        "truncation point.",
        "agent_actions.id=264; error_log.error_message='Exit code 1'",
    ),
    (
        1687,
        "Recovered command (agent_actions id 271): "
        '`sqlite3 .../dqiii8.db "SELECT score, created_at, summary FROM '
        'audit_reports ORDER BY created_at DESC L..."` -- same ad-hoc '
        "query-typo root cause as the SELECT-ts-score / SELECT-score-"
        "created_at-summary BashError patterns above (audit_reports has "
        "no score/created_at/summary columns; real columns are "
        "overall_score/timestamp). error_log's own error_message for this "
        "row holds only 'Exit code 1' with no SQL text, so it could not "
        "be caught by a message-body LIKE pattern -- resolved by id "
        "instead, using the command recovered via agent_actions.",
        "agent_actions.id=271; verified 2026-08-21 via .schema audit_reports",
    ),
]


def main() -> None:
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    total_resolved = 0
    for error_type, like_pattern, resolution, citation in KNOWN_EXPLAINED:
        cur = conn.execute(
            "UPDATE error_log SET resolved=1, resolution=? "
            "WHERE resolved=0 AND error_type=? AND error_message LIKE ?",
            (f"{resolution} ({citation})", error_type, like_pattern),
        )
        print(f"{error_type} LIKE '{like_pattern}': resolved {cur.rowcount} row(s)")
        total_resolved += cur.rowcount

    for row_id, resolution, citation in EXPLICIT_IDS:
        cur = conn.execute(
            "UPDATE error_log SET resolved=1, resolution=? WHERE resolved=0 AND id=?",
            (f"{resolution} ({citation})", row_id),
        )
        print(f"id={row_id}: resolved {cur.rowcount} row(s)")
        total_resolved += cur.rowcount
    conn.commit()

    remaining = conn.execute("SELECT count(1) FROM error_log WHERE resolved=0").fetchone()[0]
    conn.close()
    print(f"total resolved this run: {total_resolved}")
    print(f"remaining unresolved: {remaining}")


if __name__ == "__main__":
    main()
