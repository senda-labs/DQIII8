#!/usr/bin/env python3
"""
DQIII8 Health Watchdog — daily preventive maintenance check.

13+ checks (count varies: one per configured service/cron/backup-DB, plus a
conditional hooks_config_warnings when out-of-repo hook paths exist) covering
services, crons, core modules, DB integrity, disk space, import paths, backup
freshness/log, the health_check.py dead-man's-switch, abandoned human_hours
sessions, hooks config, and dependency version pins. Sends Telegram alert if
any check fails.
Silent on full success (only logs).

Usage:
    python3 bin/monitoring/health_watchdog.py
    python3 bin/monitoring/health_watchdog.py --quiet   # suppress OK output
"""

from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

DQIII8_ROOT = (
    Path(os.environ["DQIII8_ROOT"])
    if os.environ.get("DQIII8_ROOT")
    else Path(__file__).resolve().parents[2]
)
sys.path.insert(0, str(DQIII8_ROOT / "bin" / "core"))
sys.path.insert(0, str(DQIII8_ROOT / "bin" / "agents"))

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bin.core.logging_config import get_logger as _get_logger

log = _get_logger(__name__)

DB = DQIII8_ROOT / "database" / "dqiii8.db"
# repointed to SSOT (metrics.db fork was stale since 2026-03-28 — consolidation 2026-07-05)
NOW = datetime.now(timezone.utc)
QUIET = "--quiet" in sys.argv

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    status = "OK " if ok else "ERR"
    msg = f"{status}  {name}" + (f" — {detail}" if detail else "")
    if ok:
        log.info("%s", msg)
    else:
        log.error("%s", msg)
        failures.append(f"{name}: {detail}" if detail else name)


# ── Check 1: Services alive ────────────────────────────────────────────────


def check_services() -> None:
    # "autoreporte" removed 2026-08-12: no systemd unit or script by that name
    # exists anywhere in the tree — a phantom entry that always reported "down".
    for svc in ["dqiii8-bot", "dq-dashboard", "ollama"]:
        result = subprocess.run(
            ["systemctl", "is-active", svc], capture_output=True, text=True, timeout=30
        )
        check(f"service:{svc}", result.stdout.strip() == "active", result.stdout.strip())


# ── Check 2: Crons executed in last 48h ───────────────────────────────────


def check_crons() -> None:
    # (log path, tmp_backed) — tmp_backed marks logs under the real /tmp,
    # wiped at boot (tmpfiles.d 30d rule). Recorded explicitly rather than
    # inferred from the path string: nightly.sh's log is DQIII8_ROOT-relative,
    # and DQIII8_ROOT itself can be redirected under /tmp during testing,
    # which would make a string-prefix check misclassify it.
    #
    # memory_decay/sandbox_tester/auto_researcher logs moved /tmp -> var/logs
    # 2026-08-13 (Opus red-team review, P3-8): a /tmp-backed marker made a
    # post-reboot absence structurally indistinguishable from a dead cron,
    # silently converting these three checks into permanent no-ops after any
    # /tmp sweep. var/ survives reboots, so tmp_backed=False now applies.
    log_checks = {
        "nightly.sh": (DQIII8_ROOT / "tasks" / "nightly-report.md", False),
        "memory_decay": (DQIII8_ROOT / "var" / "logs" / "decay.log", False),
        "sandbox_tester": (DQIII8_ROOT / "var" / "logs" / "sandbox.log", False),
        "auto_researcher": (DQIII8_ROOT / "var" / "logs" / "researcher.log", False),
    }
    for name, (log_path, tmp_backed) in log_checks.items():
        if not log_path.exists():
            # A missing /tmp-backed log right after a reboot is expected, not
            # a failure, until the cron next runs (same reasoning as
            # check_backup_log). nightly.sh's log survives reboots, so its
            # absence is still a real failure.
            if tmp_backed:
                check(f"cron:{name}", True, "log absent (likely post-reboot /tmp wipe)")
            else:
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
        timeout=120,
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
        timeout=60,
    )
    ok = result.returncode == 0 and "OK" in result.stdout
    check("knowledge_enricher", ok, result.stderr.strip()[:80] if not ok else "")


# ── Check 5: DB integrity ─────────────────────────────────────────────────


def check_db_integrity() -> None:
    if not DB.exists():
        check("db_integrity", False, f"DB not found: {DB}")
        return
    try:
        conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=30)
        row = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        check("db_integrity", row and row[0] == "ok", row[0] if row else "no result")
    except Exception as e:
        check("db_integrity", False, str(e)[:80])


# ── Check 6: Disk space ───────────────────────────────────────────────────


def check_disk_space() -> None:
    result = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=30)
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
            timeout=30,
        )
        check(
            f"syntax:{Path(target).name}",
            result.returncode == 0,
            result.stderr.strip()[:80] if result.returncode != 0 else "",
        )


# ── Check 8: Working memory functional ────────────────────────────────────


def check_working_memory() -> None:
    code = (
        "import sys; sys.path.insert(0,'bin/agents'); sys.path.insert(0,'bin/core');"
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
        timeout=60,
    )
    ok = result.returncode == 0 and "OK" in result.stdout
    check("working_memory", ok, result.stderr.strip()[:80] if not ok else "")


# ── Check 9: Backup freshness ─────────────────────────────────────────────

BACKUP_DIR = DQIII8_ROOT / "database" / "backups"
BACKUP_DBS = ["dqiii8.db", "dqiii8_knowledge.db", "dqiii8_history.db"]
# Live counts 2026-08-12 (4/5/7 per DB) are still refilling at +1/DB/day after
# the Stage-0.1 rotation fix; a flat >=7 floor would fire on deploy. Ramps to
# the script's real KEEP=7 target by the date they're expected to reach it.
BACKUP_MIN_RETAIN = 7 if date.today() >= date(2026, 8, 19) else 3


def _parse_backup_ts(name: str, prefix: str) -> datetime | None:
    try:
        return datetime.strptime(name[len(prefix) :], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def check_backup_freshness() -> None:
    for db in BACKUP_DBS:
        prefix = f"{db}.bak-"
        candidates = [
            p
            for p in BACKUP_DIR.glob(f"{prefix}*")
            if not p.name.endswith(("-wal", "-shm", ".partial"))
        ]
        valid = [(p, ts) for p in candidates if (ts := _parse_backup_ts(p.name, prefix))]
        if not valid:
            check(f"backup_freshness:{db}", False, "no parseable backups")
            continue
        newest_ts = max(ts for _, ts in valid)
        oldest_ts = min(ts for _, ts in valid)
        age_h = (NOW - newest_ts).total_seconds() / 3600
        count = len(valid)
        ok = age_h <= 24 and count >= BACKUP_MIN_RETAIN
        check(
            f"backup_freshness:{db}",
            ok,
            f"newest {age_h:.0f}h old, count={count} (min {BACKUP_MIN_RETAIN})",
        )
        # A burst restore/reseed can create `count` backups all near the same
        # timestamp, passing the count/newest checks above identically to
        # `count` genuine daily backups. 20h not 24h: cron-jitter/day-boundary
        # tolerance, mirrors the 24h-vs-25h reasoning above.
        if count >= BACKUP_MIN_RETAIN:
            span_h = (newest_ts - oldest_ts).total_seconds() / 3600
            spread_ok = span_h >= (count - 1) * 20
            check(
                f"backup_span:{db}",
                spread_ok,
                (
                    "backups present but not aged — possible burst restore"
                    if not spread_ok
                    else f"span {span_h:.0f}h across {count} backups"
                ),
            )


# ── Check 10: Backup log ──────────────────────────────────────────────────

BACKUP_LOG = DQIII8_ROOT / "var" / "logs" / "db_backup.log"
# moved /tmp -> var/logs 2026-08-13 (Opus red-team review, P3-8) — see check_crons
_BACKUP_OK_RE = re.compile(r"^\[db_backup\] (\S+) ok: (\S+) \(")


def check_backup_log() -> None:
    # Empty, not just absent: the log path moved /tmp -> var/logs 2026-08-13,
    # so a freshly-created empty file at the new path means the 02:50 cron
    # hasn't fired since the move yet — same "not yet run" case as absent, not
    # a failure. A real failed run always writes something (db_backup.sh's own
    # error echoes go to the same fd via `2>&1`), so an empty file can't hide
    # a genuine failure — only "never invoked since this file was created".
    if not BACKUP_LOG.exists() or not BACKUP_LOG.read_text(errors="replace").strip():
        check(
            "backup_log",
            True,
            "log absent or empty (not yet run since var/logs move) — see backup_freshness",
        )
        return
    lines = BACKUP_LOG.read_text(errors="replace").splitlines()[-20:]
    parsed = []
    for line in lines:
        m = _BACKUP_OK_RE.match(line)
        if not m:
            continue
        ts_str, dst = m.groups()
        try:
            ts = datetime.strptime(ts_str, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        db_name = Path(dst).name.split(".bak-")[0]
        parsed.append((ts, db_name))
    if not parsed:
        check("backup_log", False, "no parseable 'ok:' line in last 20 lines")
        return
    newest_ts = max(ts for ts, _ in parsed)
    dbs_at_newest = {db for ts, db in parsed if ts == newest_ts}
    missing = set(BACKUP_DBS) - dbs_at_newest
    age_h = (NOW - newest_ts).total_seconds() / 3600
    detail = f"newest run {age_h:.0f}h ago"
    if missing:
        detail += f", missing at that run: {', '.join(sorted(missing))}"
    check("backup_log", age_h <= 24 and not missing, detail)


# ── Check 11: health_check.py dead-man's-switch (mutual with the heartbeat) ─

VAR_DIR = DQIII8_ROOT / "var"
HEARTBEAT_PATH = VAR_DIR / "watchdog_heartbeat"
AUDIT_REPORTS_DIR = DQIII8_ROOT / "database" / "audit_reports"
_HEALTH_JSON_RE = re.compile(r"^health_(\d{4}-\d{2}-\d{2})(?:_\d{4}|_\d{6}|_\d{12})?\.json$")


def write_heartbeat() -> None:
    VAR_DIR.mkdir(parents=True, exist_ok=True)
    HEARTBEAT_PATH.write_text(NOW.isoformat())


def check_health_check_output() -> None:
    dates = []
    for p in AUDIT_REPORTS_DIR.glob("health_*.json"):
        m = _HEALTH_JSON_RE.match(p.name)
        if not m:
            continue
        try:
            dates.append(datetime.strptime(m.group(1), "%Y-%m-%d").date())
        except ValueError:
            continue
    if not dates:
        check("health_check_output", False, "no health_*.json found")
        return
    newest = max(dates)
    age_days = (NOW.date() - newest).days
    check("health_check_output", age_days <= 1, f"newest report is {age_days}d old")


# ── Check 12: Abandoned human_hours sessions ──────────────────────────────


def check_human_hours() -> None:
    try:
        conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=30)
        n = conn.execute(
            "SELECT COUNT(*) FROM human_hours WHERE ended_at IS NULL "
            "AND (julianday('now') - julianday(started_at)) > 16.0/24.0"
        ).fetchone()[0]
        conn.close()
        check("human_hours", n == 0, f"{n} open session(s) >16h" if n else "")
    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            check("human_hours", True, "table absent")
        else:
            check("human_hours", False, str(e)[:80])


# ── Check: dependency pins ──────────────────────────────────────────────────

EXPECTED_SQLITE_VEC_VERSION = "0.1.7"


def check_dependency_pins() -> None:
    try:
        from importlib.metadata import version

        installed = version("sqlite-vec")
        check(
            "dependency_pins",
            installed == EXPECTED_SQLITE_VEC_VERSION,
            (
                f"sqlite-vec {installed} != expected {EXPECTED_SQLITE_VEC_VERSION}"
                if installed != EXPECTED_SQLITE_VEC_VERSION
                else ""
            ),
        )
    except Exception as e:
        check("dependency_pins", False, str(e)[:80])


def check_hooks_config() -> None:
    try:
        sys.path.insert(0, str(DQIII8_ROOT / "bin" / "tools"))
        from validate_hooks_config import _validate

        # Pass DQIII8_ROOT-derived path explicitly rather than importing
        # DEFAULT_SETTINGS — that constant is computed from the imported
        # module's own __file__, not DQIII8_ROOT, so under a redirected root
        # (testing) this check would silently validate the production file
        # instead (Opus red-team review, 2026-08-13, P3-4).
        settings_path = DQIII8_ROOT / ".claude" / "settings.json"
        # source="worktree" (the default) — this check's whole purpose is "is
        # the live runtime config broken right now", so it must read the
        # worktree file, never staged/committed content (round 2 P1-3).
        problems, warnings = _validate(settings_path)
        check("hooks_config", not problems, "; ".join(problems)[:200] if problems else "")
        # Surfaced, not dropped (round 2 P2-2): an out-of-repo dangling hook
        # path is a non-fatal warning by design (P2-4 below), but silently
        # discarding it here made a relocated/stale hook path undetectable
        # anywhere, not just non-blocking at commit time.
        if warnings:
            check("hooks_config_warnings", True, "; ".join(warnings)[:200])
    except Exception as e:
        check("hooks_config", False, str(e)[:80])


def check_triage_ran() -> None:
    """error_log triage (bin/tools/triage_error_log.py --apply, cron 03:50)
    has no failure signal of its own — a locked DB or crash there is silent
    otherwise (Opus red-team review, 2026-08-13, P2-1). Its own history file
    doubles as a liveness marker: it's now only written after a successful
    --apply run (dry-runs and pre-commit crashes no longer touch it), and it
    lives in var/ (survives reboot), unlike the old /tmp-backed cron logs."""
    marker = DQIII8_ROOT / "var" / "triage_history.json"
    if not marker.exists():
        # "Absence is OK" is bounded by install age (round 2 P2-4) — the
        # marker survives reboots now, so unlike the /tmp-backed logs this
        # check replaced, absence past one grace period means the cron never
        # ran once, not that the box rebooted recently. Repo's first-commit
        # timestamp, not `.git`'s own mtime — the latter is rewritten by
        # every git operation (new loose objects, refs) and doesn't reflect
        # when the repo was actually set up.
        try:
            first_commit_ts = int(
                subprocess.run(
                    ["git", "log", "--reverse", "--format=%at"],
                    cwd=DQIII8_ROOT, capture_output=True, text=True, timeout=10,
                ).stdout.splitlines()[0]
            )
            install_age_h = (NOW - datetime.fromtimestamp(first_commit_ts, tz=timezone.utc)).total_seconds() / 3600
        except (IndexError, ValueError, subprocess.SubprocessError):
            install_age_h = 0  # can't determine — don't false-alarm on a fresh/odd checkout
        check(
            "triage_ran",
            install_age_h <= 48,
            "history file absent" + (
                " (fresh install, no run yet)" if install_age_h <= 48
                else f" and install is {install_age_h:.0f}h old — triage cron may never have run"
            ),
        )
        return
    age_h = (NOW - datetime.fromtimestamp(marker.stat().st_mtime, tz=timezone.utc)).total_seconds() / 3600
    check("triage_ran", age_h <= 48, f"last successful run {age_h:.0f}h ago (limit 48h)")


# ── Main ──────────────────────────────────────────────────────────────────


CHECKS = [
    ("services", check_services),
    ("crons", check_crons),
    ("auto_learner", check_auto_learner),
    ("knowledge_enricher", check_knowledge_enricher),
    ("db_integrity", check_db_integrity),
    ("disk_space", check_disk_space),
    ("imports", check_imports),
    ("working_memory", check_working_memory),
    ("backup_freshness", check_backup_freshness),
    ("backup_log", check_backup_log),
    ("health_check_output", check_health_check_output),
    ("human_hours", check_human_hours),
    ("dependency_pins", check_dependency_pins),
    ("hooks_config", check_hooks_config),
    ("triage_ran", check_triage_ran),
]


def main() -> None:
    log.info("Starting — %s", NOW.strftime("%Y-%m-%d %H:%M UTC"))
    for name, func in CHECKS:
        try:
            func()
        except Exception as e:
            check(f"{name}:exception", False, str(e)[:80])

    try:
        write_heartbeat()
    except Exception as e:
        check("heartbeat_write", False, str(e)[:80])

    if failures:
        msg = f"DQIII8 WATCHDOG ALERT\n{NOW.strftime('%Y-%m-%d %H:%M UTC')}\n"
        msg += f"Failed checks ({len(failures)}):\n"
        msg += "\n".join(f"- {f}" for f in failures)
        log.error("ALERT — %d check(s) failed", len(failures))
        try:
            from notify import send_telegram

            res = send_telegram(msg)
            if not res.ok:
                log.error("ALERT DELIVERY FAILED: %s", res.error)
        except Exception as e:
            log.error("notify failed: %s", e, exc_info=True)
    else:
        log.info("All checks passed — system healthy")


if __name__ == "__main__":
    main()
