#!/usr/bin/env python3
"""
JARVIS Hook — PreToolUse
v3: Delegación a PermissionAnalyzer + soporte ESCALATE
"""

import json
import os
import sys
import time

# ── Parsear input ────────────────────────────────────────────────────────────
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

tool = data.get("tool_name", "")
inp = data.get("tool_input", {})
session = data.get("session_id", "unknown")
agent = data.get("agent_id", data.get("agent_name", ""))

if not agent:
    _tmp = f"/tmp/jarvis_agent_{session}.json"
    try:
        with open(_tmp, encoding="utf-8") as _f:
            agent = json.load(_f).get("agent_type", "claude-sonnet-4-6")
    except Exception:
        agent = "claude-sonnet-4-6"

# ── Importar PermissionAnalyzer ──────────────────────────────────────────────
_hooks_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _hooks_dir)

try:
    from permission_analyzer import PermissionAnalyzer, record_rejection

    _analyzer = PermissionAnalyzer()
    result = _analyzer.evaluate(tool, inp)
except Exception as _e:
    # Si el analyzer falla, dejar pasar (fail-open para no bloquear trabajo)
    result = {
        "decision": "APPROVE",
        "reason": f"analyzer_error:{_e}",
        "risk_level": "LOW",
        "rule_triggered": None,
        "suggested_fix": None,
    }

# ── Manejar DENY / ESCALATE ──────────────────────────────────────────────────
if result["decision"] in ("DENY", "ESCALATE"):
    try:
        record_rejection(tool, inp, result)
    except Exception:
        pass

    escalate_prefix = "🚨 ESCALATE" if result["decision"] == "ESCALATE" else "🔒 DENY"
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"[PermissionAnalyzer:{result['decision']}] "
                        f"{result['reason']} | "
                        f"Risk: {result['risk_level']} | "
                        f"Fix: {str(result.get('suggested_fix', 'N/A'))[:120]}"
                    ),
                }
            }
        )
    )
    sys.exit(0)

# ── Métricas de acciones (fail-silent) ──────────────────────────────────────
try:
    import sqlite3

    DB = os.path.join(
        os.environ.get("JARVIS_ROOT", "/root/jarvis"),
        "database",
        "jarvis_metrics.db",
    )
    if os.path.exists(DB):
        conn = sqlite3.connect(DB, timeout=10)
        conn.execute(
            "INSERT INTO agent_actions "
            "(session_id, agent_name, tool_used, file_path, action_type, start_time_ms) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                session,
                agent,
                tool,
                inp.get("file_path", inp.get("command", ""))[:120],
                tool.lower(),
                int(time.time() * 1000),
            ),
        )
        conn.commit()
        conn.close()
except Exception:
    pass

sys.exit(0)
