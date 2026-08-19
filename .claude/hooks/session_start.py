#!/usr/bin/env python3
"""
DQIII8 Hook — SessionStart
Injects project context, recent lessons, and system state.
"""

import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path

JARVIS = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
sys.path.insert(0, str(JARVIS / "bin"))

_log = logging.getLogger("dqiii8.session_start")
if not _log.handlers:
    _log.setLevel(logging.DEBUG)
    _log_dir = Path("/var/log/dqiii8")
    if _log_dir.exists():
        _fh = logging.handlers.RotatingFileHandler(
            str(_log_dir / "hooks.log"), maxBytes=2_000_000, backupCount=3
        )
        _fh.setFormatter(logging.Formatter("%(asctime)s [session_start] %(levelname)s %(message)s"))
        _log.addHandler(_fh)
    else:
        _log.addHandler(logging.NullHandler())

try:
    data = json.load(sys.stdin)
except Exception:
    data = {}
DB = JARVIS / "database" / "dqiii8.db"
LESSONS = JARVIS / "tasks" / "lessons.md"
FLAG = JARVIS / "tasks" / "audit_pending.flag"

# ── Active project (Correction C fix: the old resolver globbed the
# nonexistent JARVIS/projects/ dir and always fell through to dqiii8-core) ──
_cwd_str = str(Path(data.get("cwd", ".")))
try:
    from core.project_context import resolve_project

    _session_id = data.get("session_id", "")
    project = resolve_project(session_id=_session_id, cwd=_cwd_str)
except Exception as e:
    _log.warning("resolve_project failed, defaulting to dqiii8-core: %s", e, exc_info=True)
    project = "dqiii8-core"


# Seed project_context(scope=session_id) when cwd is under my-projects/, so
# later resolve_project() calls with only a session_id (no cwd) still resolve.
_session_id_for_seed = data.get("session_id", "")
if _session_id_for_seed and "/my-projects/" in _cwd_str:
    try:
        from core.project_context import set_project

        set_project(project, scope=_session_id_for_seed, declared_by="session_start", validate=False)
    except Exception as e:
        _log.debug("project_context session seed skipped: %s", e)

# Save session start time so stop.py Fallback 2 can scope to this session
try:
    Path("/tmp/dqiii8_session_start.txt").write_text(
        datetime.now().isoformat(), encoding="utf-8"
    )
except Exception as e:
    _log.debug("session-start timestamp write skipped: %s", e)

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
    lessons = [l for l in all_lines if l.strip().startswith("[20")][-5:]

# ── Last audit ─────────────────────────────────────────────────────
audit_info = "No audit yet"
try:
    import sqlite3

    if DB.exists():
        conn = sqlite3.connect(str(DB), timeout=2)
        row = conn.execute(
            "SELECT timestamp,overall_score FROM audit_reports "
            "ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if row:
            audit_info = f"{row[0][:10]} | Score: {row[1]}/100"
except Exception as e:
    _log.warning("audit-score DB failed: %s", e, exc_info=True)

# ── Pending audit alert ────────────────────────────────────────────
audit_alert = ""
if FLAG.exists():
    audit_alert = "\n⚠  AUDIT PENDING — run /audit now."
    try:
        FLAG.unlink()
    except Exception as e:
        _log.debug("audit-flag unlink skipped: %s", e)

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
except Exception as e:
    _log.warning("vault-memory DB failed: %s", e, exc_info=True)

# ── Lazy context load ──────────────────────────────────────────────
CONTEXT_DIR = JARVIS / "context"

# user_profile.md: ALWAYS (universal context ~1KB)
_user_profile_block = ""
_profile_path = CONTEXT_DIR / "user_profile.md"
if _profile_path.exists():
    _user_profile_block = "\n\nUSER PROFILE:\n" + _profile_path.read_text(
        encoding="utf-8"
    )

# youtube_channels.md: ONLY if project is content
_channels_block = ""
if project in ("content",):
    _channels_path = CONTEXT_DIR / "youtube_channels.md"
    if _channels_path.exists():
        _channels_block = "\n\nYOUTUBE CHANNELS:\n" + _channels_path.read_text(
            encoding="utf-8"
        )

# proposito.md: ONLY if exists and JARVIS_PROPOSITO=1
_proposito_block = ""
if os.environ.get("JARVIS_PROPOSITO") == "1":
    _proposito_path = CONTEXT_DIR / "proposito.md"
    if _proposito_path.exists():
        _proposito_block = "\n\nPURPOSE:\n" + _proposito_path.read_text(
            encoding="utf-8"
        )

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
                _memories_block = "\n\nRECENT MEMORIES:\n" + "\n".join(
                    f"- {m}" for m in _mems
                )
        finally:
            _sig.alarm(0)
except Exception as e:
    _log.debug("memory-manager skipped: %s", e)

model = os.environ.get("DQIII8_MODEL", "claude-sonnet-5")

# ── Personality Mode ────────────────────────────────────────────────
_MODE_BEHAVIORS = {
    "coder": "CODER MODE: code first, minimal prose, Black always, show diffs.",
    "analyst": "ANALYST MODE: tables, metrics, verify numbers, no speculation.",
    "creative": "CREATIVE MODE: narrative, literary style, no technical formatting.",
}

# Precedence: DQIII8_MODE env var → var/dqiii8_mode.conf → /tmp legacy file.
#
# The env var is only honoured when it names a real personality mode. The same
# DQIII8_MODE name is already owned by permission_analyzer.py, where it carries a
# different vocabulary ("supervised"/"autonomous"); validating against
# _MODE_BEHAVIORS keeps the two uses from colliding instead of silently
# interpreting a permission setting as a writing style.
#
# var/dqiii8_mode.conf is the file /mode writes (gitignored, survives reboot).
# /tmp/dqiii8_mode.txt is the pre-2026-08-17 location, still read so an already
# running box doesn't lose its mode mid-flight.
_mode = ""
try:
    _env_mode = os.environ.get("DQIII8_MODE", "").strip().lower()
    if _env_mode in _MODE_BEHAVIORS:
        _mode = _env_mode
    else:
        for _mode_file in (JARVIS / "var" / "dqiii8_mode.conf", Path("/tmp/dqiii8_mode.txt")):
            if _mode_file.exists():
                _candidate = _mode_file.read_text(encoding="utf-8").strip().lower()
                if _candidate:
                    _mode = _candidate
                    break
except Exception as e:
    _log.debug("mode read skipped: %s", e)

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
except Exception as e:
    _log.debug("progress-file read skipped: %s", e)

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
