#!/usr/bin/env python3
"""
DQIII8 Hook — PreToolUse v7
Thin wrapper: parse stdin → PermissionAnalyzer → RAG rules injection + output truncation.

v7 changes (ADR-001 corrections):
  - Rules RAG: injects ONLY relevant rules via rules_dispatcher.py (~200-800 tokens)
    instead of auto-loading all 16 files (~4k tokens) on every tool call.
  - Output Truncation: wraps Bash commands that may produce large output with
    truncate_output.py pipe. Uses modifiedToolInput to transform the command
    transparently — no blocking, no censorship.
  - Removed blocking OutputGuard (was censorship, not truncation).
"""

import json
import logging
import os
import re
import sys
import time

log = logging.getLogger("dqiii8." + __name__)

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

tool = data.get("tool_name", "")
inp = data.get("tool_input", {})
session = data.get("session_id", "unknown")
agent = data.get("agent_id", data.get("agent_name", ""))

if not agent:
    try:
        with open(f"/tmp/dqiii8_agent_{session}.json", encoding="utf-8") as _f:
            agent = json.load(_f).get("agent_type", "claude-sonnet-4-6")
    except Exception:
        agent = "claude-sonnet-4-6"

_HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HOOKS_DIR)
DQIII8_ROOT = os.environ.get("DQIII8_ROOT", "/root/dqiii8")
TRUNCATE_SCRIPT = os.path.join(DQIII8_ROOT, "bin", "tools", "truncate_output.py")

# ── PermissionAnalyzer ────────────────────────────────────────────────────────
try:
    from permission_analyzer import PermissionAnalyzer, record_rejection
    result = PermissionAnalyzer().evaluate(tool, inp, session_id=session)
except Exception as _e:
    result = {
        "decision": "APPROVE",
        "reason": f"analyzer_error:{_e}",
        "risk_level": "LOW",
        "rule_triggered": None,
        "suggested_fix": None,
    }

if result["decision"] in ("DENY", "ESCALATE"):
    try:
        record_rejection(tool, inp, result)
    except Exception as e:
        log.warning("pre_tool_use: record_rejection failed: %s", e, exc_info=True)
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"[PermissionAnalyzer:{result['decision']}] "
                f"{result['reason']} | Risk: {result['risk_level']} | "
                f"Fix: {str(result.get('suggested_fix', 'N/A'))[:120]}"
            ),
        }
    }))
    sys.exit(0)


# ── Metrics ───────────────────────────────────────────────────────────────────
def _model_tier(model_id: str) -> int:
    m = model_id.lower()
    if "ollama" in m or "qwen2.5-coder" in m:
        return 1
    if any(x in m for x in ("groq", "openrouter", "haiku", "nemotron", "qwen3")):
        return 2
    if any(x in m for x in ("sonnet", "opus", "claude-sonnet", "claude-opus")):
        return 3
    return 0


try:
    import sqlite3
    _DB = os.path.join(DQIII8_ROOT, "database", "dqiii8.db")
    _model = os.environ.get("DQIII8_MODEL", agent)
    _tier = _model_tier(_model)
    if os.path.exists(_DB):
        _conn = sqlite3.connect(_DB, timeout=10)
        _conn.execute(
            "INSERT INTO agent_actions "
            "(session_id,agent_name,tool_used,file_path,action_type,start_time_ms,model_tier,model_used) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (session, agent, tool,
             inp.get("file_path", inp.get("command", ""))[:120],
             tool.lower(), int(time.time() * 1000), _tier, _model),
        )
        _conn.commit()
        _conn.close()
except Exception as e:
    log.warning("pre_tool_use: agent_actions metrics insert failed: %s", e, exc_info=True)

# ── OAuth protection ──────────────────────────────────────────────────────────
_OAUTH_FILES = ["/root/.claude.json", "/root/.claude/.credentials.json"]
if tool == "Bash":
    _cmd_check = inp.get("command", "")
    for _f in _OAUTH_FILES:
        if _f in _cmd_check and any(x in _cmd_check for x in ["rm ", "truncate", "> ", "mv "]):
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"Protected: OAuth credential {_f}",
                }
            }))
            sys.exit(0)

# ── Rules RAG: inject only relevant rules ─────────────────────────────────────
_rules_context = ""
try:
    from rules_dispatcher import get_rules
    _rules_context = get_rules(tool, inp)
except Exception as e:
    log.debug("pre_tool_use: rules RAG injection failed (best-effort): %s", e)  # never block on rules injection failure

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
            r"\bls\s+-[a-zA-Z]*R\b",     # ls -R (recursive)
            r"\bps\s+aux\b(?!\s*\|)",    # full process list
            r"\bpip\s+(?:list|freeze)\b(?!\s*\|)",
        ]

        _already_piped = bool(re.search(
            r"\|\s*(?:head|tail|wc|grep|less|more|truncate_output)", _raw_cmd
        ))

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
