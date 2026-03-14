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
try:
    result = subprocess.run(
        ["git", "-C", str(JARVIS), "diff", "HEAD", "--", "tasks/lessons.md"],
        capture_output=True,
        text=True,
        timeout=5,
    )

    def _is_lesson_line(line: str) -> bool:
        """Match diff additions like '+- [2026-...' or '+[2026-...'"""
        return line.startswith("+- [20") or line.startswith("+[20")

    lessons_added = sum(1 for line in result.stdout.splitlines() if _is_lesson_line(line))
    # Fallback: si no hay cambios en working tree, revisar último commit
    if lessons_added == 0:
        last_commit = subprocess.run(
            ["git", "-C", str(JARVIS), "log", "-1", "--oneline", "--", "tasks/lessons.md"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if last_commit.stdout.strip():
            result2 = subprocess.run(
                ["git", "-C", str(JARVIS), "diff", "HEAD~1", "HEAD", "--", "tasks/lessons.md"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            lessons_added = sum(1 for line in result2.stdout.splitlines() if _is_lesson_line(line))
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
            for line in result.stdout.splitlines()
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

sys.exit(0)
