#!/usr/bin/env python3
"""
DQIII8 Hook — PreToolUse v7
Thin wrapper: parse stdin → PermissionAnalyzer → RAG rules injection + output truncation.

v7 changes (ADR-001 corrections):
  - Rules RAG: injects ONLY relevant rules via rules_dispatcher.py instead of
    auto-loading all 16 files on every tool call. The measured token range is
    NOT restated here (it drifted here silently once) — the single source is
    rules_dispatcher.py's own docstring.
  - Output Truncation: wraps Bash commands that may produce large output with
    truncate_output.py pipe. Uses modifiedToolInput to transform the command
    transparently — no blocking, no censorship.
  - Removed blocking OutputGuard (was censorship, not truncation).
"""

import json
import logging
import logging.handlers
import os
import re
import sys
import time
from pathlib import Path

log = logging.getLogger("dqiii8." + __name__)
if not log.handlers:
    log.setLevel(logging.DEBUG)
    _log_dir = Path("/var/log/dqiii8")
    if _log_dir.exists():
        _fh = logging.handlers.RotatingFileHandler(
            str(_log_dir / "hooks.log"), maxBytes=2_000_000, backupCount=3
        )
        _fh.setFormatter(
            logging.Formatter("%(asctime)s [pre_tool_use] %(levelname)s %(message)s")
        )
        log.addHandler(_fh)
    else:
        log.addHandler(logging.NullHandler())

try:
    data = json.load(sys.stdin)
except Exception as e:
    log.warning("pre_tool_use: stdin parse failed: %s", e)
    sys.exit(0)

tool = data.get("tool_name", "")
inp = data.get("tool_input", {})
session = data.get("session_id", "unknown")
_HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HOOKS_DIR)
DQIII8_ROOT = os.environ.get("DQIII8_ROOT", "/root/dqiii8")
TRUNCATE_SCRIPT = os.path.join(DQIII8_ROOT, "bin", "tools", "truncate_output.py")

_agent_id = data.get("agent_id", "") or ""
_agent_type = data.get("agent_type", "") or ""
_worktree = ""
if _agent_id and _agent_type:
    # Fase B part 3 (root fix, 2026-09-04): the harness DOES send agent_id/
    # agent_type on every subagent-issued PreToolUse call, correctly scoped
    # per subagent even under concurrent siblings — confirmed empirically via
    # the part-2 diagnostic log, not inferred. Use it directly: no LIFO guess.
    agent = _agent_type
    try:
        _direct = os.path.join(DQIII8_ROOT, "tmp", f"dqiii8_agent_{_agent_id}.json")
        if os.path.exists(_direct):
            with open(_direct, encoding="utf-8") as _f:
                _worktree = json.load(_f).get("worktree_path", "") or ""
    except Exception as e:
        log.debug("pre_tool_use: worktree lookup failed (best-effort): %s", e)
else:
    # No agent_id/agent_type on this event — a top-level session call (agent_id
    # is correctly absent there, no subagent to attribute to) or an older
    # harness version. Best-effort LIFO fallback, kept for that case only —
    # still ambiguous if 2+ siblings are open at once AND neither the harness
    # nor this fallback can identify the caller, but that combination should
    # no longer occur given the branch above handles every real subagent call.
    agent = data.get("agent_name", "") or "claude-sonnet-5"
    try:
        _reg_db = os.path.join(DQIII8_ROOT, "database", "dqiii8.db")
        if os.path.exists(_reg_db):
            import sqlite3 as _rics

            _rconn = _rics.connect(_reg_db, timeout=2)
            _rrow = _rconn.execute(
                "SELECT agent_id, agent_type FROM agent_registry WHERE parent_session=? AND end_time IS NULL "
                "ORDER BY start_time DESC LIMIT 1",
                (session,),
            ).fetchone()
            _rconn.close()
            if _rrow:
                _agent_id, agent = _rrow[0], (_rrow[1] or agent)
                _cand = os.path.join(DQIII8_ROOT, "tmp", f"dqiii8_agent_{_rrow[0]}.json")
                if os.path.exists(_cand):
                    with open(_cand, encoding="utf-8") as _f:
                        _worktree = json.load(_f).get("worktree_path", "") or ""
    except Exception as e:
        log.debug("pre_tool_use: agent lookup failed (best-effort): %s", e)

# ── PermissionAnalyzer ────────────────────────────────────────────────────────
try:
    from permission_analyzer import (
        PermissionAnalyzer,
        record_rejection,
        record_decision,
        _GOVERNANCE_WRITE_RULE_PREFIXES,
        _request_governance_approval,
        _session_has_telegram_approval,
        _dedup_anchor,
    )

    result = PermissionAnalyzer().evaluate(tool, inp, session_id=session)
except Exception as _e:
    # Fail CLOSED: a crash inside the security evaluator must DENY, never approve.
    log.error(
        "pre_tool_use: PermissionAnalyzer crashed — failing closed: %s",
        _e,
        exc_info=True,
    )
    result = {
        "decision": "DENY",
        "reason": f"analyzer_error:{type(_e).__name__} — failing closed for safety",
        "risk_level": "CRITICAL",
        "rule_triggered": "analyzer_crash",
        "suggested_fix": "Fix the analyzer error, then retry.",
    }

if result["decision"] in ("DENY", "ESCALATE"):
    _is_gov_write = result["decision"] == "ESCALATE" and any(
        (result.get("rule_triggered") or "").startswith(p)
        for p in _GOVERNANCE_WRITE_RULE_PREFIXES
    )
    _action_detail = str(inp.get("file_path", inp.get("command", "")))[:200]
    _anchor = _dedup_anchor(_action_detail) if _is_gov_write else None

    # Continued permission for this task (2026-09-04): if this exact
    # governance action was already approved via Telegram earlier in this
    # same session, skip the 45s round-trip entirely — and, just as
    # important, never touch record_rejection for it below. Repeating a
    # now-approved action must not accumulate toward the unrelated
    # repeat-rejection loop-breaker (that was the original bug: record_
    # rejection used to run unconditionally, before Telegram ever got a
    # chance to flip the decision, so an approved action still counted
    # as a rejection and a couple of retries tripped MAX_SAME_REJECTION).
    if _is_gov_write and _session_has_telegram_approval(tool, _anchor, session):
        result = {
            "decision": "APPROVE",
            "reason": (
                f"human_approved_via_telegram_earlier_this_session:"
                f"{result['rule_triggered']}"
            ),
            "risk_level": result["risk_level"],
            "rule_triggered": result["rule_triggered"],
            "suggested_fix": result.get("suggested_fix", ""),
        }

    # Governance-corpus-write ESCALATEs get an inline Si/No Telegram button
    # instead of the fire-and-forget-only notify every other ESCALATE reason
    # gets (repeat-rejection loop-breakers, private-host WebFetch, ...) —
    # those still warrant deliberate review, not a quick tap. Blocks this
    # hook invocation for up to _APPROVAL_TIMEOUT_S; on any failure (notify
    # error, timeout, no tap) `decision` stays None and `result` is left
    # exactly as evaluate() returned it, i.e. today's unmodified ESCALATE
    # behavior — this can only ever be as safe as that, never less.
    if result["decision"] in ("DENY", "ESCALATE") and _is_gov_write:
        decision = None
        try:
            entry = {
                "tool_name": tool,
                "action_detail": _action_detail,
                "reason": result["reason"],
                "rule_triggered": result["rule_triggered"],
            }
            decision = _request_governance_approval(entry)
        except Exception as e:
            log.warning(
                "pre_tool_use: governance approval wait failed: %s", e, exc_info=True
            )
        if decision is True:
            result = {
                "decision": "APPROVE",
                "reason": f"human_approved_via_telegram:{result['rule_triggered']}",
                "risk_level": result["risk_level"],
                "rule_triggered": result["rule_triggered"],
                "suggested_fix": result.get("suggested_fix", ""),
            }
        elif decision is False:
            result = {
                "decision": "DENY",
                "reason": f"Denied by human via Telegram button. {result['reason']}",
                "risk_level": result["risk_level"],
                "rule_triggered": result["rule_triggered"],
                "suggested_fix": result.get("suggested_fix", ""),
            }

    # Only NOW record — after the continued-permission check and the live
    # Telegram round-trip both had their chance to flip an ESCALATE to
    # APPROVE. A non-governance DENY/ESCALATE (rm -rf /, a repeat-rejection
    # loop-breaker, a private-host WebFetch, ...) never enters either branch
    # above, so it is recorded immediately, exactly as before.
    if result["decision"] in ("DENY", "ESCALATE"):
        try:
            record_rejection(tool, inp, result, session_id=session)
        except Exception as e:
            log.warning("pre_tool_use: record_rejection failed: %s", e, exc_info=True)
    elif _is_gov_write:
        try:
            record_decision(tool, inp, result, session_id=session)
        except Exception as e:
            log.warning("pre_tool_use: record_decision failed: %s", e, exc_info=True)

if result["decision"] in ("DENY", "ESCALATE"):
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"[PermissionAnalyzer:{result['decision']}] "
                        f"{result['reason']} | Risk: {result['risk_level']} | "
                        f"Fix: {str(result.get('suggested_fix', 'N/A'))[:120]}"
                    ),
                }
            }
        )
    )
    sys.exit(0)


# ── Metrics ───────────────────────────────────────────────────────────────────
# _model_tier()/_tier_text() below are hook-local, not shared with stop.py's
# near-identical _tier_for_model(): each hook runs as its own subprocess and a
# shared bin/core import adds sys.path fragility for a ~10-line function.
# If the tier taxonomy (C/B/A/S) ever changes, update both.
def _model_tier(model_id: str) -> int:
    m = model_id.lower()
    if "ollama" in m or "qwen2.5-coder" in m:
        return 1
    if any(x in m for x in ("groq", "openrouter", "haiku", "nemotron", "qwen3")):
        return 2
    if any(x in m for x in ("sonnet", "opus", "claude-sonnet", "claude-opus")):
        return 3
    return 0


def _tier_text(model_id: str) -> str:
    m = model_id.lower()
    if "opus" in m:
        return "S"
    if "sonnet" in m:
        return "A"
    if any(x in m for x in ("groq", "openrouter", "haiku", "nemotron", "qwen3")):
        return "B"
    if "ollama" in m or "qwen2.5-coder" in m:
        return "C"
    return "unknown"


try:
    import sqlite3

    _DB = os.path.join(DQIII8_ROOT, "database", "dqiii8.db")
    _cwd = str(data.get("cwd", "") or "")
    # core.action_log is installed code, fixed at this hook's own location —
    # it must resolve from _HOOKS_DIR, not DQIII8_ROOT (which callers/tests
    # legitimately override to relocate only the writable DB root).
    sys.path.insert(
        0, os.path.join(os.path.dirname(os.path.dirname(_HOOKS_DIR)), "bin")
    )
    from core.action_log import resolve_project_safe, generate_request_id
    from core.model_map import resolve_model

    _model = resolve_model(agent)
    _tier = _model_tier(_model)
    _project = resolve_project_safe(session, cwd=_cwd)
    # D7 corrected scope: every INSERT gets its own request_id (cardinality 1
    # for single-attempt rows like this one) so v_agent_efficiency's
    # request-level success rate covers the whole table, not just wrapper rows.
    _request_id = generate_request_id()
    if os.path.exists(_DB):
        _conn = sqlite3.connect(_DB, timeout=10)
        _conn.execute(
            "INSERT INTO agent_actions "
            "(session_id,agent_name,tool_used,file_path,action_type,start_time_ms,model_tier,model_used,project,worktree,tier,request_id,agent_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                session,
                agent,
                tool,
                # Stored untruncated — post_tool_use.py's close-out matches on the
                # untruncated file_path; a truncated INSERT vs untruncated read
                # would silently defeat that matching key.
                inp.get("file_path", inp.get("command", "")),
                tool.lower(),
                int(time.time() * 1000),
                _tier,
                _model,
                _project,
                _worktree or None,
                _tier_text(_model),
                _request_id,
                _agent_id or None,
            ),
        )
        _conn.commit()
        _conn.close()
except Exception as e:
    log.warning(
        "pre_tool_use: agent_actions metrics insert failed: %s", e, exc_info=True
    )

# ── OAuth protection (allowlist model) ───────────────────────────────────────
# Any Bash command referencing an OAuth file is DENIED unless it is a bare
# metadata check (ls/stat/test -e/-f). Allowlist beats denylist: unknown
# binaries (curl, nc, jq, wget, rsync, scp...) fail closed automatically.
#
# /root/.claude.json carries oauthAccount and customApiKeyResponses and is
# covered by nothing else in the pipeline: _credential_hit catches its sibling
# .credentials.json by basename, but not this file. Two bypasses closed
# 2026-08-18 — the block was gated on tool == "Bash", so `Read
# {"file_path": "/root/.claude.json"}` never reached it, and the match was a
# raw substring, so `cat ~/.claude.json` carried no literal to match. Paths now
# go through the same expand/normpath/realpath candidate set _credential_hit
# uses, and the read family runs the check too — with no ls/stat carve-out,
# since a read tool has no metadata-only mode.
_OAUTH_FILES = ["/root/.claude.json", "/root/.claude/.credentials.json"]
_OAUTH_READ_TOOLS = {"Read", "Grep", "Glob", "LS", "NotebookRead"}
_OAUTH_PATH_KEYS = ("file_path", "path", "notebook_path", "pattern")
_OAUTH_ALLOWED_RE = re.compile(
    r"^\s*(?:ls(?:\s+-[a-zA-Z]+)*|stat|test\s+-[ef]|\[\s+-[ef])\s+\S"
)
_OAUTH_TOKEN_SPLIT_RE = re.compile(r"""[\s'"();|&<>=`,]+""")


def _oauth_path_hit(raw: str) -> bool:
    """True if `raw` names an OAuth credential file under any spelling."""
    raw = (raw or "").strip().strip("'\"")
    if not raw:
        return False
    expanded = os.path.expandvars(os.path.expanduser(raw))
    candidates = {raw, expanded, os.path.normpath(expanded)}
    try:
        candidates.add(os.path.realpath(expanded))
    except OSError:
        pass
    return any(f in c for c in candidates for f in _OAUTH_FILES)


def _deny_oauth(detail: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"Protected: OAuth credential file referenced ({detail}). Only "
                        "bare ls/stat/test metadata checks in Bash are permitted."
                    ),
                }
            }
        )
    )
    sys.exit(0)


if tool == "Bash":
    _cmd_check = inp.get("command", "") or ""
    try:
        from permission_analyzer import _collapse_adjacent_quotes

        _cmd_scan = _collapse_adjacent_quotes(_cmd_check)
    except Exception:
        _cmd_scan = _cmd_check
    if any(_oauth_path_hit(t) for t in _OAUTH_TOKEN_SPLIT_RE.split(_cmd_scan)) or any(
        _f in _cmd_scan for _f in _OAUTH_FILES
    ):
        _has_chain = any(
            op in _cmd_check
            for op in ("|", ";", "&&", "||", ">", "<", "`", "$(", "\n", "\r")
        )
        if _has_chain or not _OAUTH_ALLOWED_RE.match(_cmd_check):
            _deny_oauth("Bash")
elif tool in _OAUTH_READ_TOOLS:
    for _key in _OAUTH_PATH_KEYS:
        _val = inp.get(_key)
        if isinstance(_val, str) and _oauth_path_hit(_val):
            _deny_oauth(f"{tool}.{_key}")

# ── Rules RAG: inject only relevant rules ─────────────────────────────────────
_rules_context = ""
try:
    from rules_dispatcher import get_rules

    _rules_context = get_rules(tool, inp, session_id=session)
except Exception as e:
    log.debug(
        "pre_tool_use: rules RAG injection failed (best-effort): %s", e
    )  # never block on rules injection failure

# ── Output Truncation: wrap large-output Bash commands ───────────────────────
# Detects commands likely to produce >3000 chars and appends the truncation
# pipe transparently. Uses modifiedToolInput — Claude Code processes this
# BEFORE executing the tool, so output is truncated at source.
_modified_cmd = None
try:
    if tool == "Bash" and os.path.exists(TRUNCATE_SCRIPT):
        _raw_cmd = inp.get("command", "").strip()
        _TRUNCATE_PIPE = f" | python3 {TRUNCATE_SCRIPT}"

        # Patterns that indicate likely large output (not already truncated)
        _LARGE_PATTERNS = [
            r"\bgit\s+log\b(?!.*-\d)(?!.*\|\s*(?:head|tail|wc|grep|truncate))",
            r"\bcat\s+\S+\.(?:log|txt|csv|json)\b(?!\s*\|)",
            r"\bfind\s+/(?!tmp)(?!.*-maxdepth\s+[12])(?!.*\|\s*(?:head|wc))",
            r"\bls\s+-[a-zA-Z]*R\b",  # ls -R (recursive)
            r"\bps\s+aux\b(?!\s*\|)",  # full process list
            r"\bpip\s+(?:list|freeze)\b(?!\s*\|)",
        ]

        _already_piped = bool(
            re.search(r"\|\s*(?:head|tail|wc|grep|less|more|truncate_output)", _raw_cmd)
        )

        if not _already_piped:
            for _pat in _LARGE_PATTERNS:
                if re.search(_pat, _raw_cmd):
                    _modified_cmd = _raw_cmd + _TRUNCATE_PIPE
                    break
except Exception:
    _modified_cmd = None  # truncation failure must never block execution

# ── Build final response ──────────────────────────────────────────────────────
_hook_out: dict = {"hookEventName": "PreToolUse"}

if _rules_context:
    _hook_out["additionalContext"] = _rules_context

if _modified_cmd:
    _hook_out["modifiedToolInput"] = {"command": _modified_cmd}

if len(_hook_out) > 1:
    print(json.dumps({"hookSpecificOutput": _hook_out}))

sys.exit(0)
