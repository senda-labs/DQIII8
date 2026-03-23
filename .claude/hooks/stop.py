#!/usr/bin/env python3
"""
DQIII8 Hook — Stop
Closes session in DB, updates lessons.md, auto-commit, audit flag.
"""

import sys, json, os, subprocess
from datetime import datetime, timedelta
from pathlib import Path

try:
    data = json.load(sys.stdin)
except Exception:
    data = {}

session = data.get("session_id", "unknown")
JARVIS = Path(os.environ.get("DQIII8_ROOT", "/root/jarvis"))
DB = JARVIS / "database" / "dqiii8.db"
LESSONS = JARVIS / "tasks" / "lessons.md"
PROJECTS = JARVIS / "projects"
NOW = datetime.now().isoformat()

# ── 0. Count lessons added this session ───────────────────────────
lessons_added = 0
result = None  # kept for instinct extraction in step 0b
try:
    # git diff for instincts (step 0b) — not used for the main count
    result = subprocess.run(
        ["git", "-C", str(JARVIS), "diff", "HEAD", "--", "tasks/lessons.md"],
        capture_output=True,
        text=True,
        timeout=5,
    )

    def _is_lesson_line(line: str) -> bool:
        """Match diff additions like '+- [2026-...' or '+[2026-...'"""
        return line.startswith("+- [20") or line.startswith("+[20")

    def _count_lesson_lines(text: str) -> int:
        """Count lesson lines with format [YYYY-...]"""
        return sum(1 for l in text.splitlines() if l.startswith("- [20") or l.startswith("[20"))

    # Correct pattern: lines_before (HEAD) vs lines_after (working tree)
    lines_before = 0
    head_show = subprocess.run(
        ["git", "-C", str(JARVIS), "show", "HEAD:tasks/lessons.md"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    if head_show.returncode == 0:
        lines_before = _count_lesson_lines(head_show.stdout)

    lines_after = (
        _count_lesson_lines(LESSONS.read_text(encoding="utf-8")) if LESSONS.exists() else 0
    )

    lessons_added = max(0, lines_after - lines_before)

    # Fallback 1: git diff of working tree (covers uncommitted lessons.md)
    if lessons_added == 0:
        diff_count = sum(1 for line in result.stdout.splitlines() if _is_lesson_line(line))
        if diff_count > 0:
            lessons_added = diff_count

    # Fallback 2: scan recent commits for additions in lessons.md
    # Only considers commits that occurred DURING this session (avoids inheriting others' lessons)
    if lessons_added == 0:
        _fb2_start: datetime | None = None
        try:
            _ts_file = Path("/tmp/jarvis_session_start.txt")
            if _ts_file.exists():
                _fb2_start = datetime.fromisoformat(_ts_file.read_text(encoding="utf-8").strip())
        except Exception:
            pass
        log_result = subprocess.run(
            ["git", "-C", str(JARVIS), "log", "--format=%H %aI", "-10", "--", "tasks/lessons.md"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for commit_line in log_result.stdout.splitlines()[:5]:
            parts = commit_line.split(None, 1)
            if len(parts) < 2:
                continue
            sha, commit_ts_str = parts[0], parts[1].strip()
            if _fb2_start:
                try:
                    commit_dt = datetime.fromisoformat(commit_ts_str).replace(tzinfo=None)
                    if commit_dt < _fb2_start:
                        continue  # commit pre-dates this session — skip
                except Exception:
                    pass
            result2 = subprocess.run(
                ["git", "-C", str(JARVIS), "diff", f"{sha}~1", sha, "--", "tasks/lessons.md"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            count2 = sum(1 for line in result2.stdout.splitlines() if _is_lesson_line(line))
            if count2 > 0:
                lessons_added = count2
                result = result2  # update for instincts
                break
except Exception:
    pass

# ── 0a-supplement. Add implicit lessons captured by post_tool_use ──
try:
    import sqlite3 as _vls3

    if DB.exists():
        _vc = _vls3.connect(str(DB), timeout=2)
        _start_row = _vc.execute(
            "SELECT MIN(start_time_ms) FROM agent_actions WHERE session_id=?",
            (session,),
        ).fetchone()
        if _start_row and _start_row[0]:
            _start_iso = datetime.fromtimestamp(_start_row[0] / 1000).strftime("%Y-%m-%d %H:%M:%S")
            _vault_count = _vc.execute(
                "SELECT COUNT(*) FROM vault_memory"
                " WHERE source='post_tool_use' AND created_at >= ?",
                (_start_iso,),
            ).fetchone()[0]
            lessons_added += _vault_count or 0
        _vc.close()
except Exception:
    pass


# ── 0a-bis. Auto-lesson detector (pattern-based, $0 cost) ────────
_auto_count = 0
_patterns_count = 0
try:
    import sys as _als

    if str(JARVIS) not in _als.path:
        _als.path.insert(0, str(JARVIS))
    from bin.auto_learner import detect_auto_lessons as _detect

    _auto_count, _patterns_count = _detect(session_id=session, db_path=str(DB))
    if _auto_count:
        lessons_added += _auto_count
        print(f"[DQIII8] {_auto_count} auto-lesson(s) detected ({_patterns_count} patterns)")
except Exception as _ale:
    pass

# ── 0b. Extract instincts from lessons.md ─────────────────────────
try:
    import sqlite3 as _sl3, re as _re

    if DB.exists() and lessons_added > 0:

        def _strip_diff_prefix(line: str) -> str:
            """Strip leading '+' and optional '- ' to get bare lesson text."""
            s = line[1:]  # remove '+'
            return s[2:] if s.startswith("- ") else s

        _diff_lines = [
            _strip_diff_prefix(line)
            for line in (result.stdout.splitlines() if result else [])
            if (line.startswith("+- [20") or line.startswith("+[20")) and len(line) > 10
        ]
        _kw_pattern = _re.compile(r"^\[[\d-]+\]\s*\[([^\]]+)\]")
        _ic = _sl3.connect(str(DB), timeout=5)
        _inserted = 0
        for _dl in _diff_lines[:3]:  # max 3 instincts per session
            _m = _kw_pattern.match(_dl.strip())
            if not _m:
                continue
            _kw = _m.group(1).strip().lower()
            _pat = _dl.strip()
            _ex = _ic.execute("SELECT id FROM instincts WHERE keyword=?", (_kw,)).fetchone()
            if _ex:
                _ic.execute(
                    "UPDATE instincts SET times_applied=times_applied+1, last_applied=? WHERE keyword=?",
                    (NOW, _kw),
                )
            else:
                _ic.execute(
                    "INSERT INTO instincts (keyword, pattern, confidence, source, project, created_at, last_applied)"
                    " VALUES (?,?,0.5,?,?,?,?)",
                    (
                        _kw,
                        _pat,
                        "lessons.md",
                        os.environ.get("JARVIS_PROJECT", "jarvis-core"),
                        NOW,
                        NOW,
                    ),
                )
                _inserted += 1
        _ic.commit()
        _ic.close()
        if _inserted:
            print(f"[DQIII8] {_inserted} instinct(s) extracted from lessons.md")
except Exception:
    pass

# ── 0c. Vault Memory extraction (session ≥ 10 min) ───────────────
try:
    import sqlite3 as _vsl3
    import json as _vjson
    import time as _vtime

    if DB.exists():
        _vconn = _vsl3.connect(str(DB), timeout=3)
        _vrow = _vconn.execute(
            "SELECT MIN(start_time_ms) FROM agent_actions WHERE session_id=?", (session,)
        ).fetchone()
        _vconn.close()
        _vfirst_ms = _vrow[0] if _vrow and _vrow[0] else None
        _vdur_min = ((_vtime.time() * 1000 - _vfirst_ms) / 60000) if _vfirst_ms else 0

        if _vdur_min >= 10:
            # Collect modified files from git diff
            _vdiff = subprocess.run(
                ["git", "-C", str(JARVIS), "diff", "--stat", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            _vfiles = [
                l.split("|")[0].strip()
                for l in _vdiff.stdout.splitlines()
                if "|" in l and not l.strip().startswith("Bin")
            ][:10]

            # Collect new lessons from earlier diff (result variable from step 0)
            _vnew_lessons = []
            if result:
                _vnew_lessons = [
                    l[1:].strip()
                    for l in result.stdout.splitlines()
                    if (l.startswith("+- [20") or l.startswith("+[20")) and len(l) > 10
                ][:5]

            if _vfiles or _vnew_lessons:
                _vprompt = (
                    "Extract 3-5 factual triples from this dev session.\n\n"
                    f"Files modified: {', '.join(_vfiles) or 'none'}\n"
                    f"New lessons: {' | '.join(_vnew_lessons) or 'none'}\n\n"
                    "Output ONLY a JSON array (no markdown fences):\n"
                    '[{"subject": "...", "predicate": "...", "object": "..."}]\n\n'
                    "Examples:\n"
                    '{"subject": "visual_matcher", "predicate": "uses_model", "object": "fal-ai/flux-pro/kontext"}\n'
                    '{"subject": "orchestrator", "predicate": "fixed_bug", "object": "asyncio_nested_loop"}\n\n'
                    "Rules: subject=file/component name, predicate=verb, object=value/status. Max 5 triples."
                )
                _venv = os.environ.copy()
                _venv.pop("CLAUDECODE", None)
                _vres = subprocess.run(
                    ["claude", "-p", _vprompt, "--model", "claude-haiku-4-5-20251001"],
                    capture_output=True,
                    text=True,
                    timeout=45,
                    env=_venv,
                )
                if _vres.returncode == 0:
                    _vraw = _vres.stdout.strip()
                    for _vfence in ["```json", "```"]:
                        if _vfence in _vraw:
                            _vraw = _vraw.split(_vfence)[1].split("```")[0].strip()
                            break
                    _vs = _vraw.find("[")
                    _ve = _vraw.rfind("]")
                    if _vs != -1 and _ve != -1:
                        _vfacts = _vjson.loads(_vraw[_vs : _ve + 1])
                        _vproject = os.environ.get("JARVIS_PROJECT", "jarvis-core")
                        _vic = _vsl3.connect(str(DB), timeout=5)
                        _vcnt = 0
                        for _vf in _vfacts[:5]:
                            _subj = str(_vf.get("subject", ""))[:100]
                            _pred = str(_vf.get("predicate", ""))[:100]
                            _obj = str(_vf.get("object", ""))[:200]
                            if _subj and _pred and _obj:
                                _vic.execute(
                                    "INSERT INTO vault_memory (subject, predicate, object, project, entry_type) "
                                    "VALUES (?, ?, ?, ?, 'lesson') "
                                    "ON CONFLICT(subject, predicate, object) DO UPDATE SET "
                                    "times_seen = times_seen + 1, last_seen = datetime('now')",
                                    (_subj, _pred, _obj, _vproject),
                                )
                                _vcnt += 1
                        _vic.commit()
                        _vic.close()
                        if _vcnt:
                            print(f"[DQIII8] {_vcnt} vault fact(s) extracted")
except Exception:
    pass

# ── 0d. Intelligence Loop — boost/decay instinct confidence ───────
try:
    import sqlite3 as _isl3
    import re as _ire

    if DB.exists():
        _ic = _isl3.connect(str(DB), timeout=5)
        _instincts = _ic.execute(
            "SELECT id, keyword, confidence, times_applied, last_applied FROM instincts"
        ).fetchall()
        if _instincts:
            # Build vault corpus (all entries as searchable text)
            _vault_corpus = " ".join(
                f"{r[0]} {r[1]} {r[2]}"
                for r in _ic.execute(
                    "SELECT subject, predicate, object FROM vault_memory"
                ).fetchall()
            ).lower()
            _now_dt = datetime.now()
            _updated = 0
            for _iid, _kw, _iconf, _tapplied, _last_applied in _instincts:
                _iconf = _iconf or 0.5
                _root = _kw.split("-")[0].lower()
                # Boost: keyword root appears 2+ times in vault_memory
                _matches = len(_ire.findall(r"\b" + _ire.escape(_root) + r"\b", _vault_corpus))
                if _matches >= 2:
                    _iconf = min(0.95, _iconf + 0.05)
                    _updated += 1
                # Decay: applied at least once but not seen in 30 days
                if _tapplied and _tapplied > 0 and _last_applied:
                    try:
                        _lap = datetime.fromisoformat(_last_applied)
                        if (_now_dt - _lap).days > 30:
                            _iconf = max(0.10, _iconf - 0.03)
                            _updated += 1
                    except Exception:
                        pass
                _ic.execute("UPDATE instincts SET confidence=? WHERE id=?", (_iconf, _iid))
            _ic.commit()
            _ic.close()
            if _updated:
                print(f"[DQIII8] intelligence loop: {_updated} instinct(s) updated")
except Exception:
    pass

# ── 1. Close session in DB ────────────────────────────────────────
try:
    _bin = os.path.join(os.environ.get("DQIII8_ROOT", "/root/jarvis"), "bin")
    if _bin not in sys.path:
        sys.path.insert(0, _bin)
    from db import get_db as _get_db

    if DB.exists():
        with _get_db(timeout=5) as conn:
            row = conn.execute(
                "SELECT COUNT(*), SUM(CASE WHEN success=0 THEN 1 ELSE 0 END),"
                " SUM(bytes_written), COUNT(DISTINCT file_path) "
                "FROM agent_actions WHERE session_id=?",
                (session,),
            ).fetchone()
            _proj = os.environ.get("JARVIS_PROJECT", "jarvis-core")
            _model = os.environ.get("JARVIS_MODEL", "claude-sonnet-4-6")
            _total_actions = row[0] or 0
            # Guard: skip ghost sessions (no tool calls = no meaningful data, avoids audit penalty)
            if _total_actions > 0:
                conn.execute(
                    """
                    INSERT INTO sessions
                    (session_id,start_time,end_time,project,model_used,
                     total_actions,total_errors,files_touched,bytes_written,lessons_added)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(session_id) DO UPDATE SET
                    end_time=excluded.end_time, project=excluded.project,
                    model_used=excluded.model_used, total_actions=excluded.total_actions,
                    total_errors=excluded.total_errors, files_touched=excluded.files_touched,
                    bytes_written=excluded.bytes_written, lessons_added=excluded.lessons_added
                """,
                    (
                        session,
                        NOW,
                        NOW,
                        _proj,
                        _model,
                        _total_actions,
                        row[1] or 0,
                        row[3] or 0,
                        row[2] or 0,
                        lessons_added,
                    ),
                )
except Exception:
    pass

# ── 1b. Reconcile error_log with agent_actions ────────────────────
try:
    import subprocess as _rec_sub

    _rec = _rec_sub.run(
        ["python3", str(JARVIS / "bin" / "reconcile_errors.py")],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if _rec.stdout.strip():
        print(_rec.stdout.strip())
except Exception as _rec_e:
    print(f"[stop] reconcile_errors skipped: {_rec_e}")

# ── 1c. Learning metrics ──────────────────────────────────────────
try:
    import sqlite3 as _lm3

    if DB.exists():
        _lm_conn = _lm3.connect(str(DB), timeout=5)
        _lm_conn.execute(
            "CREATE TABLE IF NOT EXISTS learning_metrics ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "session_id TEXT,"
            "timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,"
            "lessons_auto INTEGER DEFAULT 0,"
            "lessons_manual INTEGER DEFAULT 0,"
            "patterns_detected INTEGER DEFAULT 0"
            ")"
        )
        _lessons_manual = max(0, lessons_added - _auto_count)
        _lm_conn.execute(
            "INSERT INTO learning_metrics (session_id, lessons_auto, lessons_manual, patterns_detected)"
            " VALUES (?, ?, ?, ?)",
            (session, _auto_count, _lessons_manual, _patterns_count),
        )
        _lm_conn.commit()
        _lm_conn.close()
except Exception:
    pass

# ── 2. Auto-commit lessons.md + projects/*.md ──────────────────────
try:
    files = [str(LESSONS)] if LESSONS.exists() else []
    files += [str(p) for p in PROJECTS.glob("*.md")]
    if files:
        subprocess.run(["git", "-C", str(JARVIS), "add"] + files, capture_output=True, timeout=10)
        subprocess.run(
            [
                "git",
                "-C",
                str(JARVIS),
                "commit",
                "-m",
                f"chore(auto): session {session[:8]} {NOW[:10]}",
            ],
            capture_output=True,
            timeout=10,
        )
except Exception:
    pass

# ── 2b. Git push after auto-commit ────────────────────────────────
try:
    result = subprocess.run(
        ["git", "push", "origin", "master"], cwd=str(JARVIS), capture_output=True, timeout=30
    )
    if result.returncode == 0:
        print("[stop] git push OK")
    else:
        print(f"[stop] git push failed: {result.stderr.decode()[:100]}")
except Exception as e:
    print(f"[stop] git push error: {e}")

# ── 3. Auto-handover if session lasted 15+ minutes ────────────────
try:
    import time as _time

    if DB.exists():
        with _get_db(timeout=3) as _conn:
            _row = _conn.execute(
                "SELECT MIN(start_time_ms) FROM agent_actions WHERE session_id=?", (session,)
            ).fetchone()
        _first_ms = _row[0] if _row and _row[0] else None
        _duration_min = ((_time.time() * 1000 - _first_ms) / 60000) if _first_ms else 0

        if _duration_min >= 15:
            # Guard: maximum 1 handover commit per calendar date
            _today = NOW[:10]
            _log_today = subprocess.run(
                [
                    "git",
                    "-C",
                    str(JARVIS),
                    "log",
                    "--oneline",
                    "--since=midnight",
                    "--grep",
                    f"session handover {_today}",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            _already_committed_today = bool(_log_today.stdout.strip())

            # Collect modified files via git diff
            _diff = subprocess.run(
                ["git", "-C", str(JARVIS), "diff", "--stat", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            _files = [
                l.split("|")[0].strip()
                for l in _diff.stdout.splitlines()
                if "|" in l and not l.strip().startswith("Bin")
            ]

            # Determine active project
            _project = os.environ.get("JARVIS_PROJECT", "jarvis-core")

            # Next step from project file
            _next = "Ver projects/{}.md".format(_project)
            _pm = JARVIS / "projects" / f"{_project}.md"
            if _pm.exists():
                _lines = _pm.read_text(encoding="utf-8").splitlines()
                for _i, _l in enumerate(_lines):
                    if "Next step" in _l:
                        for _j in range(_i + 1, min(_i + 4, len(_lines))):
                            _t = _lines[_j].strip().lstrip("-").lstrip("*").strip()
                            if _t:
                                _next = _t
                                break
                        break

            # Write session handover file
            _sessions_dir = JARVIS / "sessions"
            _sessions_dir.mkdir(exist_ok=True)
            _date = NOW[:10]
            _session_path = _sessions_dir / f"{_date}_session.md"
            _idx = 2
            while _session_path.exists():
                _session_path = _sessions_dir / f"{_date}_session_{_idx}.md"
                _idx += 1

            _files_block = (
                "\n".join(f"- `{f}`" for f in _files[:20]) or "- (no committed changes)"
            )
            _duration_str = f"{int(_duration_min)}m"
            _session_md = f"""---
date: {_date}
time: {NOW[11:16]}
project: {_project}
agent_used: claude-sonnet-4-6
session_id: {session[:8]}
duration: {_duration_str}
---

# Session {_date}

## What we did
- Session of {_duration_str} · {_project}
- (See modified files below for details)

## Modified files
{_files_block}

## Next step
{_next}

## Lessons learned
{("- " + chr(10) + "- ").join(["(none this session)"]) if not lessons_added else f"- {lessons_added} lesson(s) added — see tasks/lessons.md"}
"""
            _session_path.write_text(_session_md, encoding="utf-8")

            # Git add + commit + push (maximum 1 handover commit per day)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(JARVIS),
                    "add",
                    str(_sessions_dir),
                    str(_pm) if _pm.exists() else ".",
                ],
                capture_output=True,
                timeout=10,
            )
            if not _already_committed_today:
                subprocess.run(
                    ["git", "-C", str(JARVIS), "commit", "-m", f"session handover {_date}"],
                    capture_output=True,
                    timeout=10,
                )
            if not _already_committed_today:
                subprocess.run(
                    ["git", "-C", str(JARVIS), "push", "origin", "master"],
                    capture_output=True,
                    timeout=20,
                )

            # === GEMINI REVIEW ===
            try:
                _review_check = subprocess.run(
                    ["python3", str(JARVIS / "bin" / "gemini_review.py"), "--check-only"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if "0 files" not in _review_check.stdout and _review_check.returncode == 0:
                    _log = JARVIS / "database" / "audit_reports" / "gemini_last.log"
                    subprocess.Popen(
                        ["python3", str(JARVIS / "bin" / "gemini_review.py")],
                        stdout=open(str(_log), "w", encoding="utf-8"),
                        stderr=subprocess.STDOUT,
                    )
                    print(
                        "[DQIII8] Gemini review started in background — report ready in ~5min"
                    )
            except Exception as _ge:
                print(f"[DQIII8] Gemini review skip: {_ge}")

except Exception:
    pass  # handover failure never blocks shutdown

# ── 5. SPC audit triggers (replaces simple 7-day flag) ────────────
try:
    import sys as _spc_sys

    _spc_sys.path.insert(0, str(JARVIS))
    from bin.audit_trigger import check_triggers

    _spc_result = check_triggers(session_id=session)
    if _spc_result.get("trigger"):
        _reason = _spc_result.get("reason", "SPC trigger")
        _priority = _spc_result.get("priority", "MEDIUM")
        (JARVIS / "tasks" / "audit_pending.flag").write_text(
            f"Audit pending [{_priority}] — {_reason}\n"
            "Run /audit at the start of the next session."
        )
        print(f"[DQIII8 SPC] Audit flag set — {_reason}")
except Exception as _spc_e:
    # Fallback: simple 7-day check if SPC module unavailable
    try:
        import sqlite3 as _fb_sql

        if DB.exists():
            _fb_conn = _fb_sql.connect(str(DB), timeout=3)
            _fb_row = _fb_conn.execute("SELECT MAX(timestamp) FROM audit_reports").fetchone()
            _fb_conn.close()
            _fb_last = _fb_row[0] if _fb_row and _fb_row[0] else None
            _fb_needs = True
            if _fb_last:
                _fb_needs = (datetime.now() - datetime.fromisoformat(_fb_last)) > timedelta(days=7)
            if _fb_needs:
                (JARVIS / "tasks" / "audit_pending.flag").write_text(
                    "Audit pending — run /audit at the start of the next session."
                )
    except Exception:
        pass

# ── 6. Sync context-mode events → agent_actions ───────────────────
try:
    import sys as _sys

    _sys.path.insert(0, str(JARVIS))
    from bin.observe_events import sync_context_mode_events

    sync_context_mode_events(project_dir=str(JARVIS))
except Exception as _oe:
    print(f"[observe_events] sync skipped: {_oe}")

# ── 7. Regenerate claude-progress.txt ────────────────────────────────
try:
    import json as _json
    from datetime import datetime as _dt

    _db_path = JARVIS / "database" / "dqiii8.db"
    _progress_file = JARVIS / "claude-progress.txt"

    if _db_path.exists():
        with _get_db(timeout=3) as _conn:
            _total_sessions = _conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

            _audit_row = _conn.execute(
                "SELECT overall_score, timestamp, recommendations FROM audit_reports ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
            _score = _audit_row[0] if _audit_row else 0.0
            _audit_ts = (_audit_row[1] or "")[:10] if _audit_row else "N/A"
            _recs_raw = _audit_row[2] if _audit_row else ""
            try:
                _recs = _json.loads(_recs_raw or "[]")
            except Exception:
                _recs = [_recs_raw[:200]] if _recs_raw else []

            _integrations = _conn.execute(
                "SELECT title FROM research_items WHERE status='INTEGRADO' ORDER BY id DESC LIMIT 5"
            ).fetchall()

        _now_str = _dt.now().strftime("%Y-%m-%d %H:%M")

        _lines = [
            f"# DQIII8 — Persistent Inter-session State\n",
            f"Last updated: {_now_str}\n",
            f"Total sessions: {_total_sessions}\n",
            f"Current score: {_score:.1f}/100 ({_audit_ts})\n",
            f"\n## Pending recommendations\n",
        ]
        if _recs:
            for _r in _recs[:5]:
                _lines.append(f"- {str(_r).strip()}\n")
        else:
            _lines.append("- (none)\n")

        _lines.append("\n## Last 5 integrations\n")
        if _integrations:
            for (_t,) in _integrations:
                _lines.append(f"- {_t[:80]}\n")
        else:
            _lines.append("(none yet)\n")

        _lines.append("\n## Consolidated patterns\n")
        _lessons_file = JARVIS / "tasks" / "lessons.md"
        if _lessons_file.exists():
            import re as _re

            _ltext = _lessons_file.read_text(encoding="utf-8")
            _patterns = _re.findall(r"\[PATTERN:([A-Z0-9_\-]+)\]", _ltext)
            if _patterns:
                for _p in _patterns:
                    _lines.append(f"- {_p}\n")
            else:
                _lines.append("(none yet)\n")
        else:
            _lines.append("(none yet)\n")

        _progress_file.write_text("".join(_lines), encoding="utf-8")
        print(
            f"[stop] claude-progress.txt updated ({_total_sessions} sessions, score={_score:.1f})"
        )
except Exception as _pe:
    print(f"[stop] progress update skipped: {_pe}")

sys.exit(0)
