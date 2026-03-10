#!/usr/bin/env python3
"""
JARVIS Hook — PreToolUse
Patch 4: BLOCKED_PATHS ampliado + métricas en try/except
"""
import sys, json, time, os

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

tool    = data.get("tool_name", "")
inp     = data.get("tool_input", {})
session = data.get("session_id", "unknown")
agent   = data.get("agent_id", data.get("agent_name", "unknown"))

# ── Patch 4: BLOCKED_PATHS ampliado ────────────────────────────────
BLOCKED_PATHS = [
    ".env", "secrets", "jarvis_metrics.db",
    ".claude/settings.json", "CLAUDE.md",
    "schema.sql", ".git/",
    "id_rsa", "id_ed25519", ".ssh/",
]

BLOCKED_BASH = [
    "rm -rf /", "rm -rf ~", "rm -rf $HOME",
    "DROP TABLE", "DELETE FROM agent_actions", "DROP DATABASE",
    "> /dev/sda", "mkfs", "dd if=",
]

def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"[JARVIS] {reason}"
        }
    }))
    sys.exit(0)

# ── Comprobaciones de seguridad ─────────────────────────────────────
if tool in ("Edit", "Write", "MultiEdit"):
    path = inp.get("file_path", inp.get("path", ""))
    for blocked in BLOCKED_PATHS:
        if blocked in path:
            deny(f"Escritura bloqueada: '{path}'. Modifica este archivo manualmente si es necesario.")

if tool == "Bash":
    cmd = inp.get("command", "")
    for pattern in BLOCKED_BASH:
        if pattern.lower() in cmd.lower():
            deny(f"Comando bloqueado: '{cmd[:80]}'")

# ── Patch 4: métricas en try/except — nunca bloquean trabajo real ──
try:
    import sqlite3
    DB = os.path.join(os.environ.get("JARVIS_ROOT", "/root/jarvis"),
                      "database", "jarvis_metrics.db")
    if os.path.exists(DB):
        conn = sqlite3.connect(DB, timeout=2)
        conn.execute(
            "INSERT INTO agent_actions "
            "(session_id,agent_name,tool_used,file_path,action_type,start_time_ms) "
            "VALUES (?,?,?,?,?,?)",
            (session, agent, tool,
             inp.get("file_path", inp.get("command", ""))[:120],
             tool.lower(), int(time.time() * 1000))
        )
        conn.commit()
        conn.close()
except Exception:
    pass  # logging falla silenciosamente

sys.exit(0)
