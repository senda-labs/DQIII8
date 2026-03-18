#!/usr/bin/env python3
"""
JARVIS Hook — PostCompact
Reinyecta contexto esencial tras compactación de contexto.

Dispara DESPUÉS de que context-mode termina la compactación.
Restaura: modelo activo, proyecto activo, últimas 3 lecciones, score de auditoría.
Lee precompact_state.json escrito por precompact.py para recuperar estado anterior.
Exit 0 siempre — nunca abortar.
"""

import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB = JARVIS / "database" / "jarvis_metrics.db"
LESSONS = JARVIS / "tasks" / "lessons.md"
STATE_FILE = JARVIS / "tasks" / "precompact_state.json"

try:
    data = json.load(sys.stdin)
except Exception:
    data = {}

# ── Recuperar estado pre-compact ────────────────────────────────────
pre_state: dict = {}
try:
    if STATE_FILE.exists():
        pre_state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
except Exception:
    pass

# ── Proyecto activo ─────────────────────────────────────────────────
project = pre_state.get("project") or os.environ.get("JARVIS_PROJECT", "") or "jarvis-core"

# ── Modelo activo ───────────────────────────────────────────────────
model = os.environ.get("JARVIS_MODEL", "claude-sonnet-4-6")

# ── Últimas 3 lecciones ─────────────────────────────────────────────
lessons: list[str] = []
try:
    if LESSONS.exists():
        all_lines = LESSONS.read_text(encoding="utf-8").splitlines()
        lessons = [l for l in all_lines if l.strip().startswith("[20")][-3:]
except Exception:
    pass

# ── Último score de auditoría ───────────────────────────────────────
audit_info = "Sin auditoría"
try:
    if DB.exists():
        conn = sqlite3.connect(str(DB), timeout=2)
        row = conn.execute(
            "SELECT timestamp, overall_score FROM audit_reports " "ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if row:
            audit_info = f"{row[0][:10]} | Score: {row[1]}/100"
except Exception:
    pass

# ── Próximo paso del proyecto ───────────────────────────────────────
next_step = "No definido"
pm = JARVIS / "projects" / f"{project}.md"
try:
    if pm.exists():
        lines = pm.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if "Próximo paso" in line or "Next step" in line:
                if i + 1 < len(lines) and lines[i + 1].strip():
                    next_step = lines[i + 1].strip()
                break
except Exception:
    pass

# ── Stats de la sesión antes del compact ────────────────────────────
actions_before = pre_state.get("actions_count", "?")
session_id = pre_state.get("session_id", os.environ.get("CLAUDE_SESSION_ID", "?"))

ctx = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JARVIS — PostCompact {datetime.now().strftime('%H:%M')}
Contexto compactado — estado restaurado
Modelo  : {model}
Proyecto: {project}
Próximo : {next_step}
Auditoría: {audit_info}
Acciones sesión: {actions_before}

ÚLTIMAS LECCIONES:
{chr(10).join(lessons) if lessons else '  (ninguna registrada)'}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

print(json.dumps({"additionalContext": ctx}))
sys.exit(0)
