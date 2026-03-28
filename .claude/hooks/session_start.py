#!/usr/bin/env python3
"""
DQIII8 Hook — SessionStart
Injects project context, recent lessons, and system state.
"""

import sys, json, os
from pathlib import Path
from datetime import datetime

try:
    data = json.load(sys.stdin)
except Exception:
    data = {}

JARVIS = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
DB = JARVIS / "database" / "dqiii8.db"
LESSONS = JARVIS / "tasks" / "lessons.md"
FLAG = JARVIS / "tasks" / "audit_pending.flag"

# ── Active project ─────────────────────────────────────────────────
project = os.environ.get("DQIII8_PROJECT", "")
if not project:
    cwd = Path(data.get("cwd", "."))
    for part in cwd.parts:
        if part in ("content",):
            project = part
            break
    if not project:
        project = "dqiii8-core"

# Save session start time so stop.py Fallback 2 can scope to this session
try:
    Path("/tmp/dqiii8_session_start.txt").write_text(datetime.now().isoformat(), encoding="utf-8")
except Exception:
    pass

# ── Project next step ──────────────────────────────────────────────
next_step = "Not defined"
pm = JARVIS / "projects" / f"{project}.md"
if pm.exists():
    lines = pm.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if "Próximo paso" in line or "Next step" in line:
            if i + 1 < len(lines) and lines[i + 1].strip():
                next_step = lines[i + 1].strip()
            break

# ── Last 10 lessons ────────────────────────────────────────────────
lessons = []
if LESSONS.exists():
    all_lines = LESSONS.read_text(encoding="utf-8").splitlines()
    lessons = [l for l in all_lines if l.strip().startswith("[20")][-10:]

# ── Last audit ─────────────────────────────────────────────────────
audit_info = "No audit yet"
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

# ── Pending audit alert ────────────────────────────────────────────
audit_alert = ""
if FLAG.exists():
    audit_alert = "\n⚠️  AUDIT PENDING — run /audit now."
    try:
        FLAG.unlink()
    except Exception:
        pass

# ── Vault Memory — top-8 recent facts ─────────────────────────────
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

# ── Lazy context load ──────────────────────────────────────────────
CONTEXT_DIR = JARVIS / "context"

# user_profile.md: ALWAYS (universal context ~1KB)
_user_profile_block = ""
_profile_path = CONTEXT_DIR / "user_profile.md"
if _profile_path.exists():
    _user_profile_block = "\n\nUSER PROFILE:\n" + _profile_path.read_text(encoding="utf-8")

# youtube_channels.md: ONLY if project is content
_channels_block = ""
if project in ("content",):
    _channels_path = CONTEXT_DIR / "youtube_channels.md"
    if _channels_path.exists():
        _channels_block = "\n\nYOUTUBE CHANNELS:\n" + _channels_path.read_text(encoding="utf-8")

# proposito.md: ONLY if exists and JARVIS_PROPOSITO=1
_proposito_block = ""
if os.environ.get("JARVIS_PROPOSITO") == "1":
    _proposito_path = CONTEXT_DIR / "proposito.md"
    if _proposito_path.exists():
        _proposito_block = "\n\nPURPOSE:\n" + _proposito_path.read_text(encoding="utf-8")

# ── Recent memories (vault_memory SQLite) ─────────────────────────
_memories_block = ""
try:
    import sys as _sys
    import signal as _sig

    _mm_path = JARVIS / "bin" / "memory_manager.py"
    if _mm_path.exists():
        import importlib.util as _ilu

        import io as _io

        _spec = _ilu.spec_from_file_location("memory_manager", str(_mm_path))
        _mm = _ilu.module_from_spec(_spec)
        import contextlib as _cl

        with _cl.redirect_stderr(_io.StringIO()):
            _spec.loader.exec_module(_mm)

        def _timeout_handler(signum, frame):
            raise TimeoutError

        _sig.signal(_sig.SIGALRM, _timeout_handler)
        _sig.alarm(2)
        try:
            _mems = _mm.search_memories(project, "previous session context", top_k=5)
            _sig.alarm(0)
            if _mems:
                _memories_block = "\n\nRECENT MEMORIES:\n" + "\n".join(f"- {m}" for m in _mems)
        finally:
            _sig.alarm(0)
except Exception:
    pass  # silent skip — do not block startup

model = os.environ.get("DQIII8_MODEL", "qwen2.5-coder:7b (Ollama)")

# ── Personality Mode ────────────────────────────────────────────────
_mode = ""
try:
    _mode_file = Path("/tmp/dqiii8_mode.txt")
    if _mode_file.exists():
        _mode = _mode_file.read_text(encoding="utf-8").strip()
except Exception:
    pass

_MODE_BEHAVIORS = {
    "coder": "CODER MODE: code first, minimal prose, Black always, show diffs.",
    "analyst": "ANALYST MODE: tables, metrics, verify numbers, no speculation.",
    "creative": "CREATIVE MODE: narrative, literary style, no technical formatting.",
}

_vault_block = ""
if vault_facts:
    _vault_block = "\n\nKNOWLEDGE BASE:\n" + "\n".join(f"- {f}" for f in vault_facts)

_mode_line = f"\n{_MODE_BEHAVIORS[_mode]}" if _mode in _MODE_BEHAVIORS else ""

# ── Inter-session progress block ─────────────────────────────────
_progress_block = ""
try:
    _progress_file = JARVIS / "claude-progress.txt"
    if _progress_file.exists():
        _raw = _progress_file.read_text(encoding="utf-8").strip()
        _progress_block = "\n\nPROGRESS:\n" + _raw
except Exception:
    pass

ctx = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DQIII8 — {datetime.now().strftime('%Y-%m-%d %H:%M')}
Model   : {model}
Project : {project}
Next    : {next_step}{audit_alert}
Last audit: {audit_info}{_mode_line}{_progress_block}{_vault_block}{_memories_block}{_user_profile_block}{_channels_block}{_proposito_block}

RECENT LESSONS:
{chr(10).join(lessons) if lessons else '  (none yet)'}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

print(json.dumps({"additionalContext": ctx}))
sys.exit(0)
