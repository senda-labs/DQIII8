#!/usr/bin/env python3
"""
JARVIS Hook — PreToolUse
v4: PermissionAnalyzer + PresupuestoSesión + Modo Autónomo
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

# ── Permission Supervisor ─────────────────────────────────────────────────────
JARVIS_MODE = os.getenv("JARVIS_MODE", "supervised")

AUTO_APPROVE_TOOLS = {
    "Read",
    "Glob",
    "Grep",
    "LS",
    "Write",
    "Edit",
    "MultiEdit",
    "Bash",
    "WebFetch",
    "WebSearch",
}

# Presupuesto de sesión — bloquear si se supera $5 en la última hora
MAX_SESSION_COST_USD = 5.0
try:
    import sqlite3

    _db = os.path.join(
        os.environ.get("JARVIS_ROOT", "/root/jarvis"), "database", "jarvis_metrics.db"
    )
    conn = sqlite3.connect(_db, timeout=10)
    row = conn.execute(
        "SELECT COALESCE(SUM(tokens_used),0) FROM agent_actions "
        "WHERE session_id=? AND timestamp > datetime('now','-1 hour')",
        (data.get("session_id", ""),),
    ).fetchone()
    conn.close()
    session_tokens = row[0] if row else 0
    # Sonnet: ~$15/M tokens output — estimación conservadora
    estimated_cost = (session_tokens / 1_000_000) * 15.0
    if estimated_cost > MAX_SESSION_COST_USD:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": (
                            f"Presupuesto de sesión excedido: "
                            f"${estimated_cost:.2f} > ${MAX_SESSION_COST_USD}"
                        ),
                    }
                }
            )
        )
        sys.exit(0)
except Exception:
    pass  # Si falla el check de presupuesto, no bloquear

# En modo autonomous: auto-aprobar si ya pasó los checks de seguridad
if JARVIS_MODE == "autonomous" and tool in AUTO_APPROVE_TOOLS:
    sys.exit(0)  # Aprobación silenciosa

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
