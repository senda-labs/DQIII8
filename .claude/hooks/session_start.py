#!/usr/bin/env python3
"""
JARVIS Hook — SessionStart
Inyecta contexto del proyecto, últimas lecciones y estado del sistema.
"""

import sys, json, os
from pathlib import Path
from datetime import datetime

try:
    data = json.load(sys.stdin)
except Exception:
    data = {}

JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB = JARVIS / "database" / "jarvis_metrics.db"
LESSONS = JARVIS / "tasks" / "lessons.md"
FLAG = JARVIS / "tasks" / "audit_pending.flag"

# ── Proyecto activo ────────────────────────────────────────────────
project = os.environ.get("JARVIS_PROJECT", "")
if not project:
    cwd = Path(data.get("cwd", "."))
    for part in cwd.parts:
        if part in ("content-automation", "hult-finance", "leyendas-del-este"):
            project = part
            break
    if not project:
        project = "jarvis-core"

# ── Próximo paso del proyecto ──────────────────────────────────────
next_step = "No definido"
pm = JARVIS / "projects" / f"{project}.md"
if pm.exists():
    lines = pm.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if "Próximo paso" in line or "Next step" in line:
            if i + 1 < len(lines) and lines[i + 1].strip():
                next_step = lines[i + 1].strip()
            break

# ── Últimas 10 lecciones ───────────────────────────────────────────
lessons = []
if LESSONS.exists():
    all_lines = LESSONS.read_text(encoding="utf-8").splitlines()
    lessons = [l for l in all_lines if l.strip().startswith("[20")][-10:]

# ── Última auditoría ───────────────────────────────────────────────
audit_info = "Sin auditoría aún"
try:
    import sqlite3

    if DB.exists():
        conn = sqlite3.connect(str(DB), timeout=2)
        row = conn.execute(
            "SELECT timestamp,overall_score FROM audit_reports " "ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if row:
            audit_info = f"{row[0][:10]} | Score: {row[1]}/100"
except Exception:
    pass

# ── Alerta auditoría pendiente ─────────────────────────────────────
audit_alert = ""
if FLAG.exists():
    audit_alert = "\n⚠️  AUDITORÍA PENDIENTE — ejecuta /audit ahora."
    try:
        FLAG.unlink()
    except Exception:
        pass

# ── Vault Memory — top-8 hechos recientes ─────────────────────────
vault_facts = []
try:
    import sqlite3 as _vsl3

    if DB.exists():
        _vc = _vsl3.connect(str(DB), timeout=2)
        _vrows = _vc.execute(
            "SELECT subject, predicate, object, entry_type FROM vault_memory "
            "WHERE project=? OR project='' "
            "ORDER BY CASE entry_type "
            "  WHEN 'adr' THEN 1 "
            "  WHEN 'project_state' THEN 2 "
            "  WHEN 'lesson' THEN 3 "
            "  WHEN 'checkpoint' THEN 4 "
            "  ELSE 5 END, last_seen DESC LIMIT 8",
            (project,),
        ).fetchall()
        _vc.close()
        vault_facts = [f"{r[0]} {r[1]} {r[2]}" for r in _vrows]
except Exception:
    pass

model = os.environ.get("JARVIS_MODEL", "qwen2.5-coder:7b (Ollama)")

_vault_block = ""
if vault_facts:
    _vault_block = "\n\nKNOWLEDGE BASE:\n" + "\n".join(f"- {f}" for f in vault_facts)

ctx = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JARVIS — {datetime.now().strftime('%Y-%m-%d %H:%M')}
Modelo  : {model}
Proyecto: {project}
Próximo : {next_step}{audit_alert}
Última auditoría: {audit_info}{_vault_block}

LECCIONES RECIENTES:
{chr(10).join(lessons) if lessons else '  (ninguna aún)'}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

print(json.dumps({"additionalContext": ctx}))
sys.exit(0)
