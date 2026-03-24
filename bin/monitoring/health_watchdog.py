#!/usr/bin/env python3
"""
DQIII8 Health Watchdog — daily preventive maintenance check.

8 checks covering services, crons, core modules, DB integrity,
disk space, and import paths. Sends Telegram alert if any check fails.
Silent on full success (only logs).

Usage:
    python3 bin/monitoring/health_watchdog.py
    python3 bin/monitoring/health_watchdog.py --quiet   # suppress OK output
"""

from __future__ import annotations

import os
import subprocess
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

DQIII8_ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
sys.path.insert(0, str(DQIII8_ROOT / "bin" / "core"))
sys.path.insert(0, str(DQIII8_ROOT / "bin" / "agents"))

DB = DQIII8_ROOT / "database" / "jarvis_metrics.db"
NOW = datetime.now(timezone.utc)
QUIET = "--quiet" in sys.argv

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    status = "OK " if ok else "ERR"
    if not QUIET or not ok:
        print(f"[WATCHDOG] {status}  {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(f"{name}: {detail}" if detail else name)


# ── Check 1: Services alive ────────────────────────────────────────────────


def check_services() -> None:
    for svc in ["autoreporte", "jarvis-bot", "dq-dashboard", "ollama"]:
        result = subprocess.run(
            ["systemctl", "is-active", svc], capture_output=True, text=True
        )
        check(
            f"service:{svc}", result.stdout.strip() == "active", result.stdout.strip()
        )


# ── Check 2: Crons executed in last 48h ───────────────────────────────────


def check_crons() -> None:
    threshold = NOW - timedelta(hours=48)
    log_checks = {
        "nightly.sh": DQIII8_ROOT / "tasks" / "nightly-report.md",
        "memory_decay": Path("/tmp/jarvis_decay.log"),
        "sandbox_tester": Path("/tmp/jarvis_sandbox.log"),
        "auto_researcher": Path("/tmp/jarvis_researcher.log"),
    }
    for name, log_path in log_checks.items():
        if not log_path.exists():
            check(f"cron:{name}", False, "log file missing")
            continue
        mtime = datetime.fromtimestamp(log_path.stat().st_mtime, tz=timezone.utc)
        age_h = (NOW - mtime).total_seconds() / 3600
        # auto_researcher runs weekly — allow 8 days grace
        limit = 192 if name == "auto_researcher" else 48
        check(
            f"cron:{name}",
            age_h <= limit,
            f"last run {age_h:.0f}h ago (limit {limit}h)",
        )


# ── Check 3: Auto-learner functional ──────────────────────────────────────


def check_auto_learner() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(DQIII8_ROOT / "bin" / "tools" / "auto_learner.py"),
            "--consolidate",
            "--db",
            str(DB),
        ],
        capture_output=True,
        text=True,
        cwd=str(DQIII8_ROOT),
    )
    check(
        "auto_learner",
        result.returncode == 0,
        result.stderr.strip()[:80] if result.returncode != 0 else "",
    )


# ── Check 4: Knowledge enricher functional ────────────────────────────────


def check_knowledge_enricher() -> None:
    code = (
        "import sys; sys.path.insert(0,'bin/agents'); sys.path.insert(0,'bin/core');"
        "from knowledge_enricher import enrich_with_knowledge;"
        "r=enrich_with_knowledge('what is photosynthesis','natural_sciences');"
        "print('OK' if isinstance(r,tuple) else 'FAIL')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(DQIII8_ROOT),
    )
    ok = result.returncode == 0 and "OK" in result.stdout
    check("knowledge_enricher", ok, result.stderr.strip()[:80] if not ok else "")


# ── Check 5: DB integrity ─────────────────────────────────────────────────


def check_db_integrity() -> None:
    if not DB.exists():
        check("db_integrity", False, f"DB not found: {DB}")
        return
    try:
        conn = sqlite3.connect(str(DB), timeout=5)
        row = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        check("db_integrity", row and row[0] == "ok", row[0] if row else "no result")
    except Exception as e:
        check("db_integrity", False, str(e)[:80])


# ── Check 6: Disk space ───────────────────────────────────────────────────


def check_disk_space() -> None:
    result = subprocess.run(["df", "-h", "/"], capture_output=True, text=True)
    try:
        pct_str = result.stdout.splitlines()[1].split()[4].rstrip("%")
        pct = int(pct_str)
        check("disk_space", pct <= 85, f"{pct}% used")
    except Exception as e:
        check("disk_space", False, str(e)[:60])


# ── Check 7: Critical import paths ────────────────────────────────────────


def check_imports() -> None:
    targets = [
        "bin/core/openrouter_wrapper.py",
        "bin/agents/domain_classifier.py",
        "bin/agents/intent_amplifier.py",
        "bin/tools/auto_learner.py",
        ".claude/hooks/stop.py",
    ]
    for target in targets:
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", target],
            capture_output=True,
            text=True,
            cwd=str(DQIII8_ROOT),
        )
        check(
            f"syntax:{Path(target).name}",
            result.returncode == 0,
            result.stderr.strip()[:80] if result.returncode != 0 else "",
        )


# ── Check 8: Working memory functional ────────────────────────────────────


def check_working_memory() -> None:
    code = (
        "import sys; sys.path.insert(0,'bin/core');"
        "from working_memory import save_exchange, get_session_context;"
        "sid='watchdog_test_001';"
        "save_exchange(sid,'ping','pong','general');"
        "ctx=get_session_context(sid);"
        "print('OK' if 'ping' in ctx else 'FAIL')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(DQIII8_ROOT),
    )
    ok = result.returncode == 0 and "OK" in result.stdout
    check("working_memory", ok, result.stderr.strip()[:80] if not ok else "")


# ── Main ──────────────────────────────────────────────────────────────────


def main() -> None:
    print(f"[WATCHDOG] Starting — {NOW.strftime('%Y-%m-%d %H:%M UTC')}")
    check_services()
    check_crons()
    check_auto_learner()
    check_knowledge_enricher()
    check_db_integrity()
    check_disk_space()
    check_imports()
    check_working_memory()

    if failures:
        msg = f"DQIII8 WATCHDOG ALERT\n{NOW.strftime('%Y-%m-%d %H:%M UTC')}\n"
        msg += f"Failed checks ({len(failures)}/{8}):\n"
        msg += "\n".join(f"- {f}" for f in failures)
        print(f"\n[WATCHDOG] ALERT — {len(failures)} check(s) failed")
        try:
            from notify import send_telegram

            send_telegram(msg)
        except Exception as e:
            print(f"[WATCHDOG] notify failed: {e}", file=sys.stderr)
    else:
        print(f"[WATCHDOG] All checks passed — system healthy")


if __name__ == "__main__":
    main()
