#!/usr/bin/env python3
"""
DQIII8 — Local Health Auditor
100% offline — no LLM, no API keys required. Works on Tier C.

Usage:
    python3 bin/auditor_local.py [--json] [--period DAYS]

Exit codes:
    0  HEALTHY  (score >= 85)
    1  WARNING  (score 70-84)
    2  CRITICAL (score < 70)
"""

import argparse
import json
import os
import py_compile
import shutil
import sqlite3
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

JARVIS_ROOT = Path(os.environ.get("JARVIS_ROOT", "/root/jarvis"))
DB = JARVIS_ROOT / "database" / "jarvis_metrics.db"
HOOKS_DIR = JARVIS_ROOT / ".claude" / "hooks"
REPORTS_DIR = JARVIS_ROOT / "database" / "audit_reports"


# ── DB connection ─────────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    return sqlite3.connect(str(DB), timeout=5)


# ── Component 1: Action Success Rate (30%) ───────────────────────────────────

def check_action_success(conn: sqlite3.Connection, period_days: int) -> tuple[float, dict]:
    row = conn.execute(
        "SELECT ROUND(AVG(success) * 100, 1), COUNT(*) "
        "FROM agent_actions WHERE timestamp > datetime('now', ?)",
        (f"-{period_days} days",),
    ).fetchone()
    rate = row[0] if row[0] is not None else 100.0
    count = row[1] or 0
    return rate, {"total_actions": count}


# ── Component 2: Error Resolution Rate (30%) ─────────────────────────────────

def check_error_resolution(conn: sqlite3.Connection, period_days: int) -> tuple[float, dict]:
    row = conn.execute(
        "SELECT "
        "  COUNT(CASE WHEN resolved = 1 THEN 1 END) * 100.0 / MAX(COUNT(*), 1), "
        "  COUNT(*), "
        "  COUNT(CASE WHEN resolved = 0 THEN 1 END) "
        "FROM error_log WHERE timestamp > datetime('now', ?)",
        (f"-{period_days} days",),
    ).fetchone()
    # No errors in period → perfect score
    rate = row[0] if (row and row[1] and row[1] > 0) else 100.0
    total = row[1] or 0
    unresolved_count = row[2] or 0
    return rate, {"total_errors": total, "unresolved_count": unresolved_count}


def get_unresolved_errors(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT timestamp, error_type, error_message "
        "FROM error_log WHERE resolved = 0 "
        "ORDER BY timestamp DESC LIMIT 10",
    ).fetchall()
    return [{"timestamp": r[0], "error_type": r[1], "message": r[2]} for r in rows]


# ── Component 3: Hook Integrity (20%) ────────────────────────────────────────

def check_hook_integrity() -> tuple[float, dict]:
    if not HOOKS_DIR.exists():
        return 100.0, {"total": 0, "valid": 0, "note": "hooks dir absent"}

    hook_files = sorted(HOOKS_DIR.glob("*.py"))
    if not hook_files:
        return 100.0, {"total": 0, "valid": 0, "note": "no .py hooks"}

    valid = 0
    syntax_errors: list[str] = []
    for hook in hook_files:
        try:
            py_compile.compile(str(hook), doraise=True)
            valid += 1
        except py_compile.PyCompileError as exc:
            syntax_errors.append(f"{hook.name}: {exc}")

    score = (valid / len(hook_files)) * 100
    return score, {"total": len(hook_files), "valid": valid, "errors": syntax_errors}


# ── Component 4: Learning Rate (10%) ─────────────────────────────────────────

def check_learning_rate(conn: sqlite3.Connection, period_days: int) -> tuple[float, dict]:
    target = 5  # lessons / week
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM learning_metrics "
            "WHERE timestamp > datetime('now', ?)",
            (f"-{period_days} days",),
        ).fetchone()
        count = row[0] or 0
    except sqlite3.OperationalError:
        return 50.0, {"count": 0, "target": target, "note": "table missing — fresh install"}

    if count == 0:
        return 50.0, {"count": 0, "target": target, "note": "fresh install"}

    score = min(count / target * 100, 100.0)
    return score, {"count": count, "target": target}


# ── Component 5: System Health (10%) ─────────────────────────────────────────

def check_system_health() -> tuple[float, dict]:
    checks: dict = {}
    score = 0

    # DB accessible
    checks["db_accessible"] = DB.exists()
    if checks["db_accessible"]:
        score += 25

    # Disk < 90%
    try:
        usage = shutil.disk_usage("/")
        disk_pct = usage.used / usage.total * 100
        checks["disk_pct"] = round(disk_pct, 1)
        checks["disk_ok"] = disk_pct < 90
        if checks["disk_ok"]:
            score += 25
    except OSError:
        checks["disk_ok"] = False

    # RAM available > 500 MB — read /proc/meminfo (no psutil dep)
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                avail_mb = int(line.split()[1]) // 1024
                checks["ram_mb"] = avail_mb
                checks["ram_ok"] = avail_mb > 500
                if checks["ram_ok"]:
                    score += 25
                break
    except (OSError, ValueError, IndexError):
        checks["ram_ok"] = False

    # Ollama responding (localhost:11434)
    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/tags",
            headers={"User-Agent": "auditor_local/1.0"},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            checks["ollama_ok"] = resp.status == 200
            if checks["ollama_ok"]:
                score += 25
    except Exception:
        checks["ollama_ok"] = False

    return float(score), checks


# ── Score and labels ──────────────────────────────────────────────────────────

def compute_score(c1: float, c2: float, c3: float, c4: float, c5: float) -> float:
    return round(c1 * 0.30 + c2 * 0.30 + c3 * 0.20 + c4 * 0.10 + c5 * 0.10, 1)


def status_label(score: float) -> str:
    if score >= 85:
        return "HEALTHY"
    if score >= 70:
        return "WARNING"
    return "CRITICAL"


# ── Output formatting ─────────────────────────────────────────────────────────

def format_terminal(components: dict, score: float, unresolved: list[dict]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    label = status_label(score)

    c1 = components["action_success"]
    c2 = components["error_resolution"]
    c3 = components["hook_integrity"]
    c4 = components["learning_rate"]
    c5 = components["system_health"]

    c4_raw = f"{c4['meta']['count']}/{c4['meta']['target']}"

    lines = [
        "═══ DQ Health Audit (Local) ═══",
        f"Date: {now}",
        f"Action Success Rate:    {c1['rate']:5.1f}% (30%)  → {c1['rate'] * 0.30:.1f}/30",
        f"Error Resolution Rate:  {c2['rate']:5.1f}% (30%)  → {c2['rate'] * 0.30:.1f}/30",
        f"Hook Integrity:        {c3['score']:5.1f}% (20%)  → {c3['score'] * 0.20:.1f}/20",
        f"Learning Rate:          {c4_raw:>5}  (10%)  → {c4['score'] * 0.10:.1f}/10",
        f"System Health:         {c5['score']:5.1f}% (10%)  → {c5['score'] * 0.10:.1f}/10",
        f"HEALTH SCORE: {score}/100 — {label}",
    ]

    if unresolved:
        lines.append(f"Unresolved errors ({len(unresolved)}):")
        for err in unresolved:
            ts = (err["timestamp"] or "")[:16]
            lines.append(f"  [{ts}] {err['message']}")

    lines.append("═" * 31)
    return "\n".join(lines)


# ── Persistence ───────────────────────────────────────────────────────────────

def _write_report_file(report_text: str) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")
    path = REPORTS_DIR / f"audit-local-{ts}.md"
    path.write_text(f"```\n{report_text}\n```\n", encoding="utf-8")
    return path


def _register_in_db(
    conn: sqlite3.Connection,
    score: float,
    report_path: Path,
    components: dict,
) -> None:
    try:
        conn.execute(
            "INSERT INTO audit_reports "
            "(period_start, period_end, report_path, "
            " total_actions, global_success_rate, overall_score) "
            "VALUES (datetime('now', '-7 days'), datetime('now'), ?, ?, ?, ?)",
            (
                str(report_path),
                components["action_success"]["meta"]["total_actions"],
                components["action_success"]["rate"],
                score,
            ),
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass  # schema mismatch on older installations — non-fatal


# ── Main ─────────────────────────────────────────────────────────────────────

def run(period_days: int = 7, as_json: bool = False) -> int:
    if not DB.exists():
        print(f"[auditor_local] ERROR: DB not found at {DB}", file=sys.stderr)
        return 2

    conn = _conn()
    try:
        s1, s1_meta = check_action_success(conn, period_days)
        s2, s2_meta = check_error_resolution(conn, period_days)
        s3, s3_meta = check_hook_integrity()
        s4, s4_meta = check_learning_rate(conn, period_days)
        s5, s5_meta = check_system_health()
        unresolved = get_unresolved_errors(conn)
    finally:
        conn.close()

    components = {
        "action_success":   {"rate": s1, "meta": s1_meta},
        "error_resolution": {"rate": s2, "meta": s2_meta},
        "hook_integrity":   {"score": s3, "meta": s3_meta},
        "learning_rate":    {"score": s4, "meta": s4_meta},
        "system_health":    {"score": s5, "meta": s5_meta},
    }

    score = compute_score(s1, s2, s3, s4, s5)

    if as_json:
        print(json.dumps({
            "score": score,
            "status": status_label(score),
            "components": components,
            "unresolved_errors": unresolved,
        }, indent=2))
        return 0 if score >= 85 else (1 if score >= 70 else 2)

    report_text = format_terminal(components, score, unresolved)
    print(report_text)

    # Persist
    conn2 = _conn()
    try:
        path = _write_report_file(report_text)
        _register_in_db(conn2, score, path, components)
        print(f"Report: {path}", file=sys.stderr)
    finally:
        conn2.close()

    return 0 if score >= 85 else (1 if score >= 70 else 2)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="DQ Local Health Auditor — no LLM required",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exit codes: 0=HEALTHY  1=WARNING  2=CRITICAL",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    parser.add_argument("--period", type=int, default=7, metavar="DAYS",
                        help="Analysis window in days (default: 7)")
    args = parser.parse_args()
    sys.exit(run(period_days=args.period, as_json=args.json))


if __name__ == "__main__":
    main()
