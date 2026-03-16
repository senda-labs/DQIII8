#!/usr/bin/env python3
"""
JARVIS Statusline — muestra métricas de sesión en una línea.
Uso: python3 bin/statusline.py [--json]

Optimizado para <200ms: solo 3 queries indexed, sin joins pesados.
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB = JARVIS / "database" / "jarvis_metrics.db"
SESSION_ID = os.environ.get("CLAUDE_SESSION_ID", "")
AS_JSON = "--json" in sys.argv


def _db_query(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list:
    try:
        return conn.execute(sql, params).fetchall()
    except Exception:
        return []


def main() -> None:
    metrics: dict = {
        "project": "jarvis-core",
        "session_min": 0,
        "actions": 0,
        "blocked": 0,
        "tokens": 0,
        "audit_score": None,
        "vault_facts": 0,
    }

    if not DB.exists():
        _print(metrics, AS_JSON)
        return

    conn = sqlite3.connect(str(DB), timeout=3)
    conn.row_factory = sqlite3.Row

    # Active session
    if SESSION_ID:
        rows = _db_query(
            conn,
            "SELECT project, started_at FROM sessions WHERE session_id=? LIMIT 1",
            (SESSION_ID,),
        )
        if rows:
            metrics["project"] = rows[0][0] or "jarvis-core"
            started = rows[0][1]
            if started:
                try:
                    dt = datetime.fromisoformat(started)
                    delta = datetime.now() - dt.replace(tzinfo=None)
                    metrics["session_min"] = int(delta.total_seconds() / 60)
                except Exception:
                    pass

        rows = _db_query(
            conn,
            "SELECT COUNT(*), COALESCE(SUM(tokens_used),0), "
            "SUM(CASE WHEN blocked_by_hook=1 THEN 1 ELSE 0 END) "
            "FROM agent_actions WHERE session_id=?",
            (SESSION_ID,),
        )
        if rows:
            metrics["actions"] = rows[0][0] or 0
            metrics["tokens"] = rows[0][1] or 0
            metrics["blocked"] = rows[0][2] or 0

    # Last audit score
    rows = _db_query(
        conn,
        "SELECT overall_score FROM audit_reports ORDER BY timestamp DESC LIMIT 1",
    )
    if rows:
        metrics["audit_score"] = rows[0][0]

    # Vault facts count
    rows = _db_query(conn, "SELECT COUNT(*) FROM vault_memory")
    if rows:
        metrics["vault_facts"] = rows[0][0] or 0

    conn.close()
    _print(metrics, AS_JSON)


def _print(m: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(m))
        return

    score_str = f"Score: {m['audit_score']}/100" if m["audit_score"] is not None else "Score: —"
    vault_str = f"Vault: {m['vault_facts']}" if m["vault_facts"] else ""
    parts = [
        f"JARVIS [{m['project']}]",
        f"Sesión: {m['session_min']}m",
        f"Acciones: {m['actions']}",
        f"Bloqueados: {m['blocked']}",
        f"Tokens: {m['tokens']:,}",
        score_str,
    ]
    if vault_str:
        parts.append(vault_str)
    print(" │ ".join(parts))


if __name__ == "__main__":
    main()
