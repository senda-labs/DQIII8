#!/usr/bin/env python3
"""
JARVIS Hook — PreToolUse v5
Thin wrapper: parse stdin → PermissionAnalyzer → handle result + metrics.
Toda la lógica de permisos (budget, JARVIS_MODE, ALLOWED_DELETIONS…)
vive exclusivamente en permission_analyzer.py.
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
        with open(f"/tmp/jarvis_agent_{session}.json", encoding="utf-8") as _f:
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
        os.environ.get("JARVIS_ROOT", "/root/jarvis"), "database", "jarvis_metrics.db"
    )
    _model = os.environ.get("JARVIS_MODEL", agent)
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

sys.exit(0)
