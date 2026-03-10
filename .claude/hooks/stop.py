#!/usr/bin/env python3
"""
JARVIS Hook — Stop
Cierra sesión en BD, actualiza lessons.md, auto-commit, flag de auditoría.
"""
import sys, json, os, subprocess
from datetime import datetime, timedelta
from pathlib import Path

try:
    data = json.load(sys.stdin)
except Exception:
    data = {}

session = data.get("session_id", "unknown")
JARVIS  = Path(os.environ.get("JARVIS_ROOT", r"C:\jarvis"))
DB      = JARVIS / "database" / "jarvis_metrics.db"
LESSONS = JARVIS / "tasks" / "lessons.md"
PROJECTS = JARVIS / "projects"
NOW     = datetime.now().isoformat()

# ── 1. Cerrar sesión en BD ─────────────────────────────────────────
try:
    import sqlite3
    if DB.exists():
        conn = sqlite3.connect(str(DB), timeout=5)
        row = conn.execute(
            "SELECT COUNT(*), SUM(CASE WHEN success=0 THEN 1 ELSE 0 END),"
            " SUM(bytes_written), COUNT(DISTINCT file_path) "
            "FROM agent_actions WHERE session_id=?", (session,)
        ).fetchone()
        conn.execute("""
            INSERT INTO sessions
            (session_id,start_time,end_time,total_actions,total_errors,
             files_touched,bytes_written)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(session_id) DO UPDATE SET
            end_time=excluded.end_time, total_actions=excluded.total_actions,
            total_errors=excluded.total_errors, files_touched=excluded.files_touched,
            bytes_written=excluded.bytes_written
        """, (session, NOW, NOW,
              row[0] or 0, row[1] or 0, row[3] or 0, row[2] or 0))
        conn.commit()
        conn.close()
except Exception:
    pass

# ── 2. Auto-commit lessons.md + projects/*.md ──────────────────────
try:
    files = [str(LESSONS)] if LESSONS.exists() else []
    files += [str(p) for p in PROJECTS.glob("*.md")]
    if files:
        subprocess.run(["git","-C",str(JARVIS),"add"]+files,
                       capture_output=True, timeout=10)
        subprocess.run(["git","-C",str(JARVIS),"commit","-m",
                        f"chore(auto): session {session[:8]} {NOW[:10]}"],
                       capture_output=True, timeout=10)
except Exception:
    pass

# ── 3. Flag de auditoría si han pasado 7+ días ────────────────────
try:
    import sqlite3
    if DB.exists():
        conn = sqlite3.connect(str(DB), timeout=3)
        row  = conn.execute(
            "SELECT MAX(timestamp) FROM audit_reports"
        ).fetchone()
        conn.close()
        last = row[0] if row and row[0] else None
        needs = True
        if last:
            needs = (datetime.now()-datetime.fromisoformat(last)) > timedelta(days=7)
        if needs:
            (JARVIS/"tasks"/"audit_pending.flag").write_text(
                "Auditoría pendiente — ejecuta /audit al inicio de la próxima sesión."
            )
except Exception:
    pass

sys.exit(0)
