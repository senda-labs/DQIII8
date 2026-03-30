#!/usr/bin/env python3
"""
DQIII8 Hook — PreToolUse v6
Thin wrapper: parse stdin → PermissionAnalyzer → handle result + metrics.
All permission logic (budget, DQIII8_MODE, ALLOWED_DELETIONS…)
lives exclusively in permission_analyzer.py.

v6: Output Guard — detects commands likely to produce >100 lines of output
    and denies them with a truncation suggestion to protect context budget.
"""

import json
import os
import sys
import time

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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
    except Exception:
        pass
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


def _model_tier(model_id: str) -> int:
    """Return tier (1/2/3) for a model identifier string."""
    m = model_id.lower()
    if "ollama" in m or "qwen2.5-coder" in m:
        return 1
    if any(x in m for x in ("groq", "openrouter", "haiku", "nemotron", "qwen3")):
        return 2
    if any(x in m for x in ("sonnet", "opus", "claude-sonnet", "claude-opus")):
        return 3
    return 0  # unknown


try:
    import sqlite3

    _DB = os.path.join(
        os.environ.get("DQIII8_ROOT", "/root/dqiii8"), "database", "dqiii8.db"
    )
    _model = os.environ.get("DQIII8_MODEL", agent)
    _tier = _model_tier(_model)
    if os.path.exists(_DB):
        _conn = sqlite3.connect(_DB, timeout=10)
        _conn.execute(
            "INSERT INTO agent_actions "
            "(session_id,agent_name,tool_used,file_path,action_type,start_time_ms,model_tier,model_used) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                session,
                agent,
                tool,
                inp.get("file_path", inp.get("command", ""))[:120],
                tool.lower(),
                int(time.time() * 1000),
                _tier,
                _model,
            ),
        )
        _conn.commit()
        _conn.close()
except Exception:
    pass

# Additional protection: OAuth credentials (before sys.exit)
_OAUTH_FILES = ["/root/.claude.json", "/root/.claude/.credentials.json"]
if tool in ("Bash",):
    cmd = inp.get("command", "")
    for _f in _OAUTH_FILES:
        if _f in cmd and any(x in cmd for x in ["rm ", "truncate", "> ", "mv "]):
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": f"Protected: OAuth credential {_f}",
                        }
                    }
                )
            )
            sys.exit(0)

# ── Output Guard v6: protect context budget from large Bash outputs ──────────
try:
    import re as _re

    _LARGE_OUTPUT_PATTERNS = [
        # git log without -N limit
        (_re.compile(r"git\s+log(?!\s+--oneline\s+-\d)(?!.*-\d+\b)(?!.*\|\s*head)"),
         "git log -20 --oneline"),
        # find without maxdepth on wide paths
        (_re.compile(r"\bfind\s+/(?!tmp)(?!.*-maxdepth\s+[12])(?!.*\|\s*head)"),
         "find / -maxdepth 3 … | head -50"),
        # cat on large files without head
        (_re.compile(r"\bcat\s+\S+\.(log|txt|json|csv)(?!\s*\|)"),
         "head -100 <file> or use the Read tool"),
        # ls -la on root-level dirs
        (_re.compile(r"\bls\s+-[a-zA-Z]*la?\s+(/[a-z]+/?)\s*$"),
         "ls -la <dir> | head -50"),
        # unfiltered git diff without stat
        (_re.compile(r"\bgit\s+diff\b(?!.*--stat)(?!.*\|\s*head)(?!.*\|\s*wc)"),
         "git diff --stat or git diff | head -100"),
    ]

    if tool == "Bash":
        _cmd = inp.get("command", "").strip()
        for _pat, _fix in _LARGE_OUTPUT_PATTERNS:
            if _pat.search(_cmd):
                print(
                    json.dumps(
                        {
                            "hookSpecificOutput": {
                                "hookEventName": "PreToolUse",
                                "permissionDecision": "deny",
                                "permissionDecisionReason": (
                                    f"[OutputGuard] Command may produce >100 lines — "
                                    f"context budget protected. "
                                    f"Suggested fix: {_fix}"
                                ),
                            }
                        }
                    )
                )
                sys.exit(0)
except Exception:
    pass  # output guard must never block execution on error

sys.exit(0)
