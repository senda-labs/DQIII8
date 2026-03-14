#!/usr/bin/env python3
"""
JARVIS Hook — PostToolUse
Patch 5: bloque SQLite en try/except — nunca bloquea trabajo real
Auto-format Python con Black tras cada edición.
"""

import sys, json, time, os, subprocess

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

tool = data.get("tool_name", "")
inp = data.get("tool_input", {})
resp = data.get("tool_response", {}) or {}
session = data.get("session_id", "unknown")
agent = data.get("agent_id", data.get("agent_name", "unknown"))
now_ms = int(time.time() * 1000)

# ── Auto-format Python ──────────────────────────────────────────────
if tool in ("Edit", "Write", "MultiEdit"):
    path = inp.get("file_path", inp.get("path", ""))
    if path and path.endswith(".py"):
        try:
            subprocess.run(["black", "--quiet", path], capture_output=True, timeout=10)
        except Exception:
            pass

# ── Patch 5: métricas en try/except — nunca bloquean trabajo real ──
try:
    import sqlite3

    DB = os.path.join(
        os.environ.get("JARVIS_ROOT", "/root/jarvis"), "database", "jarvis_metrics.db"
    )
    if os.path.exists(DB):
        success = 1 if resp.get("exit_code", 0) == 0 else 0
        error_msg = (resp.get("stderr") or resp.get("error") or "")[:500]
        content = inp.get("new_content", inp.get("content", ""))
        bytes_wr = len(content.encode("utf-8", errors="replace")) if content else 0
        # Cuando falla sin stderr: registrar tool + motivo genérico para auditoría
        stored_error = error_msg or (f"{tool} falló (sin stderr)" if not success else None)

        conn = sqlite3.connect(DB, timeout=2)
        # Cerrar la acción abierta por pre_tool_use (más reciente sin end_time)
        conn.execute(
            """
            UPDATE agent_actions
            SET end_time_ms=?, duration_ms=?-COALESCE(start_time_ms,?),
                success=?, error_message=?, bytes_written=?
            WHERE id=(
                SELECT id FROM agent_actions
                WHERE session_id=? AND tool_used=? AND end_time_ms IS NULL
                ORDER BY id DESC LIMIT 1)
        """,
            (now_ms, now_ms, now_ms, success, stored_error, bytes_wr, session, tool),
        )

        if not success:
            conn.execute(
                "INSERT INTO error_log "
                "(session_id,agent_name,error_type,error_message,keywords) "
                "VALUES (?,?,?,?,?)",
                (session, agent, f"{tool}Error", stored_error or f"{tool} failed", "[]"),
            )
        conn.commit()
        conn.close()
except Exception:
    pass  # logging falla silenciosamente

sys.exit(0)
