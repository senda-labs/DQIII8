#!/usr/bin/env python3
"""
DQIII8 — SQLite MCP wrapper
Expone dqiii8.db como MCP server stdio para Claude Code.
Uso: python sqlite_mcp.py [ruta_a_db]
"""
import sys, json, sqlite3, os
from pathlib import Path

DB_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else \
          Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8")) / "database" / "dqiii8.db"

def respond(id_, result=None, error=None):
    out = {"jsonrpc": "2.0", "id": id_}
    if error:
        out["error"] = {"code": -32000, "message": str(error)}
    else:
        out["result"] = result
    print(json.dumps(out), flush=True)

def handle(req):
    method = req.get("method", "")
    params = req.get("params", {})
    id_    = req.get("id")

    if method == "initialize":
        respond(id_, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "dqiii8-sqlite", "version": "1.0"}
        })

    elif method == "tools/list":
        respond(id_, {"tools": [
            {"name": "query",
             "description": "Execute a read-only SQL query on dqiii8.db",
             "inputSchema": {
                 "type": "object",
                 "properties": {"sql": {"type": "string"}},
                 "required": ["sql"]
             }},
            {"name": "execute",
             "description": "Execute a write SQL statement (INSERT/UPDATE)",
             "inputSchema": {
                 "type": "object",
                 "properties": {"sql": {"type": "string"},
                                "params": {"type": "array"}},
                 "required": ["sql"]
             }}
        ]})

    elif method == "tools/call":
        tool   = params.get("name")
        args   = params.get("arguments", {})
        sql    = args.get("sql", "")
        p      = args.get("params", [])

        # Block destructive operations
        sql_upper = sql.strip().upper()
        if any(sql_upper.startswith(w) for w in ("DROP","DELETE","TRUNCATE","ALTER")):
            respond(id_, error="Destructive SQL blocked. Use SELECT, INSERT, UPDATE only.")
            return

        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=5)
            conn.row_factory = sqlite3.Row
            if tool == "query":
                rows = conn.execute(sql, p).fetchall()
                data = [dict(r) for r in rows]
                respond(id_, {"content": [{"type":"text","text":json.dumps(data,indent=2)}]})
            elif tool == "execute":
                cur = conn.execute(sql, p)
                conn.commit()
                respond(id_, {"content": [{"type":"text","text":f"Rows affected: {cur.rowcount}"}]})
            conn.close()
        except Exception as e:
            respond(id_, error=str(e))

    elif method == "notifications/initialized":
        pass  # no response needed

    else:
        respond(id_, error=f"Method not found: {method}")

# ── Main loop ───────────────────────────────────────────────────────
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
        handle(req)
    except json.JSONDecodeError:
        pass
    except Exception as e:
        print(json.dumps({"jsonrpc":"2.0","id":None,
                          "error":{"code":-32700,"message":str(e)}}), flush=True)
