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
JARVIS = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB = JARVIS / "database" / "jarvis_metrics.db"
LESSONS = JARVIS / "tasks" / "lessons.md"
PROJECTS = JARVIS / "projects"
NOW = datetime.now().isoformat()

# ── 0. Contar lecciones añadidas esta sesión ───────────────────────
lessons_added = 0
result = None  # mantenido para extracción de instincts en paso 0b
try:
    # git diff para instincts (paso 0b) — no se usa para el conteo principal
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
        """Cuenta líneas de lección con formato [YYYY-...]"""
        return sum(1 for l in text.splitlines() if l.startswith("- [20") or l.startswith("[20"))

    # Patrón correcto: líneas_antes (HEAD) vs líneas_después (working tree)
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

    # Fallback 1: git diff del working tree (cubre lessons.md no commitado aún)
    if lessons_added == 0:
        diff_count = sum(1 for line in result.stdout.splitlines() if _is_lesson_line(line))
        if diff_count > 0:
            lessons_added = diff_count

    # Fallback 2: recorrer commits recientes hasta encontrar adiciones en lessons.md
    # (cubre el caso donde lessons.md fue commitado durante la sesión y hubo más commits después)
    if lessons_added == 0:
        log_result = subprocess.run(
            ["git", "-C", str(JARVIS), "log", "--oneline", "-10", "--", "tasks/lessons.md"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for commit_line in log_result.stdout.splitlines()[:3]:
            sha = commit_line.split()[0]
            result2 = subprocess.run(
                ["git", "-C", str(JARVIS), "diff", f"{sha}~1", sha, "--", "tasks/lessons.md"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            count2 = sum(1 for line in result2.stdout.splitlines() if _is_lesson_line(line))
            if count2 > 0:
                lessons_added = count2
                result = result2  # actualizar para instincts
                break
except Exception:
    pass


# ── 0b. Extraer instincts de lessons.md ───────────────────────────
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
            print(f"[JARVIS] {_inserted} instinct(s) extraidos de lessons.md")
except Exception:
    pass

# ── 0c. Vault Memory extraction (sesión ≥ 10 min) ────────────────
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
                            print(f"[JARVIS] {_vcnt} vault fact(s) extracted")
except Exception:
    pass

# ── 1. Cerrar sesión en BD ─────────────────────────────────────────
try:
    import sqlite3

    if DB.exists():
        conn = sqlite3.connect(str(DB), timeout=5)
        row = conn.execute(
            "SELECT COUNT(*), SUM(CASE WHEN success=0 THEN 1 ELSE 0 END),"
            " SUM(bytes_written), COUNT(DISTINCT file_path) "
            "FROM agent_actions WHERE session_id=?",
            (session,),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO sessions
            (session_id,start_time,end_time,total_actions,total_errors,
             files_touched,bytes_written,lessons_added)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(session_id) DO UPDATE SET
            end_time=excluded.end_time, total_actions=excluded.total_actions,
            total_errors=excluded.total_errors, files_touched=excluded.files_touched,
            bytes_written=excluded.bytes_written, lessons_added=excluded.lessons_added
        """,
            (session, NOW, NOW, row[0] or 0, row[1] or 0, row[3] or 0, row[2] or 0, lessons_added),
        )
        conn.commit()
        conn.close()
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

# ── 2b. Git push después del auto-commit ──────────────────────────
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

# ── 3. Auto-handover si sesión duró 15+ minutos ───────────────────
try:
    import sqlite3, time as _time

    if DB.exists():
        _conn = sqlite3.connect(str(DB), timeout=3)
        _row = _conn.execute(
            "SELECT MIN(start_time_ms) FROM agent_actions WHERE session_id=?", (session,)
        ).fetchone()
        _conn.close()
        _first_ms = _row[0] if _row and _row[0] else None
        _duration_min = ((_time.time() * 1000 - _first_ms) / 60000) if _first_ms else 0

        if _duration_min >= 15:
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
                    if "Próximo paso" in _l or "Proximo paso" in _l or "Next step" in _l:
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
                "\n".join(f"- `{f}`" for f in _files[:20]) or "- (sin cambios commiteados)"
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

# Sesión {_date}

## Qué hicimos
- Sesión de {_duration_str} · {_project}
- (Ver archivos modificados abajo para detalle)

## Archivos modificados
{_files_block}

## Próximo paso
{_next}

## Lecciones aprendidas
{("- " + chr(10) + "- ").join(["(ninguna esta sesión)"]) if not lessons_added else f"- {lessons_added} lección(es) añadidas — ver tasks/lessons.md"}
"""
            _session_path.write_text(_session_md, encoding="utf-8")

            # Git add + commit + push
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
            subprocess.run(
                ["git", "-C", str(JARVIS), "commit", "-m", f"📝 session handover {_date}"],
                capture_output=True,
                timeout=10,
            )
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
                if "0 archivos" not in _review_check.stdout and _review_check.returncode == 0:
                    _log = JARVIS / "database" / "audit_reports" / "gemini_last.log"
                    subprocess.Popen(
                        ["python3", str(JARVIS / "bin" / "gemini_review.py")],
                        stdout=open(str(_log), "w", encoding="utf-8"),
                        stderr=subprocess.STDOUT,
                    )
                    print(
                        "[JARVIS] Gemini review iniciado en background — reporte en Obsidian en ~5min"
                    )
            except Exception as _ge:
                print(f"[JARVIS] Gemini review skip: {_ge}")

except Exception:
    pass  # handover failure never blocks shutdown

# ── 5. Flag de auditoría si han pasado 7+ días ────────────────────
try:
    import sqlite3

    if DB.exists():
        conn = sqlite3.connect(str(DB), timeout=3)
        row = conn.execute("SELECT MAX(timestamp) FROM audit_reports").fetchone()
        conn.close()
        last = row[0] if row and row[0] else None
        needs = True
        if last:
            needs = (datetime.now() - datetime.fromisoformat(last)) > timedelta(days=7)
        if needs:
            (JARVIS / "tasks" / "audit_pending.flag").write_text(
                "Auditoría pendiente — ejecuta /audit al inicio de la próxima sesión."
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

sys.exit(0)
