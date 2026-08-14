#!/usr/bin/env python3
"""One-time consolidation of DQIII8's 3 SQLite DBs into 2.

Implements docs/superpowers/specs/2026-08-14-db-consolidation-design.md §5.3
(reviewed by an independent 3-Opus panel, 2026-08-14) and
~/.claude/plans/resilient-snuggling-parrot.md step by step. Read both before
running this against production.

What this does, in order:
  0. dry-run checks (always runs; nothing below executes unless they pass
     AND --execute is given)
  1. timestamped backup of the 3 live DBs
  2. integrity_check on the 3 live DBs
  3. stop writers (services + systemd timers + cron)
  4. integrity_check on dqiii8_metrics.db immediately before copying it
  5. transfer session_memory from dqiii8_history.db into dqiii8.db — this is
     a schema change to database/schema_v2.sql (the SSOT). Requires the
     --execute flag same as every other step; there is no separate runtime
     prompt because the required "STOP, notify, wait" was satisfied by the
     user approving the plan this script implements, before this script was
     written. Do not lower that bar by adding an --i-approve-schema-change
     escape hatch here.
  6. create dqiii8_knowledge.db via `.backup` (NOT VACUUM INTO — VACUUM INTO
     resets journal_mode from wal to delete, changing concurrency on the
     hot knowledge_usage write path)
  7. retire dqiii8_metrics.db -> dqiii8_metrics.db.old (no DROP — see spec
     §5.3 for why the DROP was removed from the design entirely)
  8. NOT done here — code path fixes (11 modules + working_memory.py + 6
     infra files) are a separate commit per the plan, applied by hand
     between step 7 and step 9 of a real run. This script pauses and tells
     you to do that before continuing.
  9. light VACUUM on dqiii8.db
  10. chmod 600 on dqiii8_knowledge.db
  11. restart writers (always runs, even on failure — try/finally)

Usage:
    python3 bin/tools/db_consolidate.py                 # dry-run only (step 0), no mutation
    python3 bin/tools/db_consolidate.py --execute        # runs steps 1-7, then pauses for step 8
    python3 bin/tools/db_consolidate.py --execute --resume-after-code-fixes
                                                          # runs steps 9-11 after step 8 is done by hand

MUST be run from outside a Claude Code session (plain SSH/tmux) — the
PreToolUse/PostToolUse hooks of a live CC session write to agent_actions /
error_log / vault_memory on every tool call, which are 3 of the 10 tables
step 0's overlap-zero check treats as "no active writer". Running this
script itself via the Bash tool from inside Claude Code would make the
calling session lie to its own dry-run check.
"""

import argparse
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_DIR = ROOT / "database"
DB_MAIN = DB_DIR / "dqiii8.db"
DB_METRICS = DB_DIR / "dqiii8_metrics.db"
DB_HISTORY = DB_DIR / "dqiii8_history.db"
DB_KNOWLEDGE = DB_DIR / "dqiii8_knowledge.db"
SCHEMA_PATH = DB_DIR / "schema_v2.sql"
BACKUP_ROOT = DB_DIR / "backups"

sys.path.insert(0, str(ROOT))
from bin.core.logging_config import get_logger  # noqa: E402

log = get_logger("tools.db_consolidate")

# spec §2.2 — 10 tables active in dqiii8.db today whose pre-2026-03-28
# history lives only in dqiii8_metrics.db. Overlap must stay 0 right up to
# execution; a nonzero overlap means an undetected writer touched one of
# these since the spec's analysis was done.
OVERLAP_ZERO_TABLES = [
    "error_log", "amplification_log", "sessions", "learning_metrics",
    "permission_decisions", "audit_reports", "research_items",
    "agent_registry", "instincts", "vault_memory",
]

WRITER_UNITS = [
    "dqiii8-bot", "dq-dashboard", "cron",
    "hpt-poller.timer", "dqiii8-health.timer",
]

SESSION_MEMORY_DDL = """CREATE TABLE IF NOT EXISTS session_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    domain TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)"""

SESSION_MEMORY_COLUMNS = ["session_id", "role", "content", "domain", "timestamp"]


class AbortMigration(Exception):
    """Raised by any step to stop the run cleanly (finally still restarts writers)."""


def _sh(cmd: list, check: bool = True) -> subprocess.CompletedProcess:
    log.info("run: %s", " ".join(cmd))
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def _integrity_check(db_path: Path) -> str:
    conn = sqlite3.connect(f"file:{db_path}?immutable=1", uri=True)
    try:
        return conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()


def _table_overlap(main_db: Path, other_db: Path, table: str) -> int:
    """Row-count of the INTERSECT between the two tables on ALL shared columns.

    Content-based, not id-based — id sequences are independent per DB (spec
    §0). ATTACH is read-only here; nothing is written to either DB.
    """
    conn = sqlite3.connect(f"file:{main_db}?immutable=1", uri=True)
    try:
        conn.execute("ATTACH DATABASE ? AS other", (f"file:{other_db}?immutable=1",))
        cols_main = [r[1] for r in conn.execute(f"PRAGMA main.table_info({table})")]
        cols_other = [r[1] for r in conn.execute(f"PRAGMA other.table_info({table})")]
        shared = [c for c in cols_main if c in cols_other]
        if not shared:
            return 0
        col_list = ", ".join(shared)
        query = (
            f"SELECT COUNT(*) FROM ("
            f"SELECT {col_list} FROM main.{table} "
            f"INTERSECT "
            f"SELECT {col_list} FROM other.{table})"
        )
        return conn.execute(query).fetchone()[0]
    finally:
        conn.close()


def step0_dry_run() -> None:
    log.info("=== step 0: dry-run checks ===")

    for db in (DB_MAIN, DB_METRICS, DB_HISTORY):
        if not db.exists():
            raise AbortMigration(f"missing DB: {db}")

    for table in OVERLAP_ZERO_TABLES:
        overlap = _table_overlap(DB_MAIN, DB_METRICS, table)
        if overlap != 0:
            raise AbortMigration(
                f"overlap-zero check failed for {table}: {overlap} shared rows "
                f"— an undetected writer has touched this table since the spec's "
                f"analysis. Do not proceed."
            )
        log.info("overlap check ok: %s (0 shared rows)", table)

    for db, label in ((DB_MAIN, "main"), (DB_METRICS, "metrics"), (DB_HISTORY, "history")):
        conn = sqlite3.connect(f"file:{db}?immutable=1", uri=True)
        try:
            cur = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name='session_memory'"
            )
            has_table = cur.fetchone()[0] > 0
            count = None
            if has_table:
                count = conn.execute("SELECT COUNT(*) FROM session_memory").fetchone()[0]
            log.info("session_memory in %s: exists=%s count=%s", label, has_table, count)
        finally:
            conn.close()

    free_bytes = shutil.disk_usage(DB_DIR).free
    metrics_size = DB_METRICS.stat().st_size
    # copy (.backup) + timestamped backup of all 3 + headroom
    needed = metrics_size * 3
    if free_bytes < needed:
        raise AbortMigration(
            f"insufficient disk space: {free_bytes} free, need ~{needed}"
        )
    log.info("disk space ok: %d bytes free, ~%d needed", free_bytes, needed)

    timers = _sh(["systemctl", "list-timers", "--all", "--no-legend"], check=False)
    for unit in ("hpt-poller.timer", "dqiii8-health.timer"):
        for line in timers.stdout.splitlines():
            if unit in line:
                log.info("timer state: %s", line.strip())

    git_status = _sh(["git", "status", "--short"], check=False)
    if git_status.stdout.strip():
        raise AbortMigration(
            "working tree not clean:\n" + git_status.stdout +
            "\ncommit or discard before running this migration (plan precondition)"
        )
    log.info("git tree clean")

    log.info("=== step 0 passed ===")


def step1_backup() -> Path:
    log.info("=== step 1: timestamped backup ===")
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out_dir = BACKUP_ROOT / f"pre-consolidation-{ts}"
    out_dir.mkdir(parents=True, exist_ok=False)
    # sqlite3 .backup (not VACUUM INTO) — preserves journal_mode and is safe
    # against a live WAL db, same reasoning as step 6. Same mechanism as
    # bin/tools/db_backup.sh's daily backup.
    for db in (DB_MAIN, DB_METRICS, DB_HISTORY):
        dst = out_dir / db.name
        _sh(["sqlite3", str(db), f".backup '{dst}'"])
        dst.chmod(0o600)
        log.info("backed up %s -> %s (%d bytes)", db.name, dst, dst.stat().st_size)
    return out_dir


def step2_integrity_check() -> None:
    log.info("=== step 2: integrity_check on live DBs ===")
    for db in (DB_MAIN, DB_METRICS, DB_HISTORY):
        result = _integrity_check(db)
        if result != "ok":
            raise AbortMigration(f"integrity_check failed for {db.name}: {result}")
        log.info("integrity_check ok: %s", db.name)


def step3_stop_writers() -> None:
    log.info("=== step 3: stop writers ===")
    _sh(["systemctl", "stop"] + WRITER_UNITS)
    log.info("stopped: %s", ", ".join(WRITER_UNITS))
    leftover = _sh(
        ["pgrep", "-af", "python3.*(dqiii8|bin/)"], check=False
    )
    if leftover.stdout.strip():
        log.warning(
            "python processes still alive after stopping units — inspect before "
            "continuing:\n%s", leftover.stdout
        )


def step4_metrics_integrity_check() -> None:
    log.info("=== step 4: integrity_check on dqiii8_metrics.db (pre-copy) ===")
    result = _integrity_check(DB_METRICS)
    if result != "ok":
        raise AbortMigration(f"integrity_check failed for {DB_METRICS.name}: {result}")
    log.info("integrity_check ok: %s", DB_METRICS.name)


def step5_transfer_session_memory() -> None:
    log.info("=== step 5: transfer session_memory (schema change to schema_v2.sql) ===")

    conn_hist = sqlite3.connect(f"file:{DB_HISTORY}?immutable=1", uri=True)
    try:
        frozen_count = conn_hist.execute("SELECT COUNT(*) FROM session_memory").fetchone()[0]
    finally:
        conn_hist.close()
    log.info("frozen session_memory count in history: %d", frozen_count)

    schema_text = SCHEMA_PATH.read_text()
    if "CREATE TABLE IF NOT EXISTS session_memory" in schema_text:
        log.info("session_memory already declared in schema_v2.sql — skipping append")
    else:
        addition = (
            "\n-- session_memory: migrated from dqiii8_history.db into the SSOT "
            "(db-consolidation 2026-08-14, panel-reviewed). Definition copied "
            "verbatim from the live dqiii8_history.db instance.\n"
            f"{SESSION_MEMORY_DDL};\n"
        )
        SCHEMA_PATH.write_text(schema_text.rstrip() + "\n" + addition)
        log.info("appended session_memory to schema_v2.sql")

    _sh(["sqlite3", str(DB_MAIN), f".read {SCHEMA_PATH}"])
    log.info("applied schema_v2.sql to dqiii8.db")

    conn = sqlite3.connect(str(DB_MAIN))
    try:
        conn.execute("ATTACH DATABASE ? AS history", (str(DB_HISTORY),))
        col_list = ", ".join(SESSION_MEMORY_COLUMNS)
        conn.execute(
            f"INSERT OR IGNORE INTO session_memory ({col_list}) "
            f"SELECT {col_list} FROM history.session_memory"
        )
        conn.commit()
        result_count = conn.execute("SELECT COUNT(*) FROM session_memory").fetchone()[0]
    finally:
        conn.close()

    if result_count != frozen_count:
        raise AbortMigration(
            f"session_memory transfer count mismatch: history had {frozen_count}, "
            f"dqiii8.db has {result_count} after transfer. Do not proceed to step 6."
        )
    log.info("session_memory transfer verified: %d rows", result_count)


def step6_create_knowledge_db() -> None:
    log.info("=== step 6: create dqiii8_knowledge.db via .backup ===")
    if DB_KNOWLEDGE.exists():
        raise AbortMigration(f"{DB_KNOWLEDGE} already exists — refusing to overwrite")

    _sh(["sqlite3", str(DB_METRICS), f".backup '{DB_KNOWLEDGE}'"])

    result = _integrity_check(DB_KNOWLEDGE)
    if result != "ok":
        raise AbortMigration(f"integrity_check failed for {DB_KNOWLEDGE.name}: {result}")

    conn_src = sqlite3.connect(f"file:{DB_METRICS}?immutable=1", uri=True)
    conn_dst = sqlite3.connect(f"file:{DB_KNOWLEDGE}?immutable=1", uri=True)
    try:
        src_count = conn_src.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type IN ('table','view')"
        ).fetchone()[0]
        dst_count = conn_dst.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type IN ('table','view')"
        ).fetchone()[0]
        if src_count != dst_count:
            raise AbortMigration(
                f"table+view count mismatch after copy: source={src_count} "
                f"dest={dst_count}"
            )
        log.info("table+view count matches: %d", dst_count)

        # vec0 virtual table can't be COUNT()'d without the sqlite-vec
        # extension loaded — verify via its shadow rowid table instead
        # (spec §5.3 step 6 / panel seat 1 finding #8).
        src_vec = conn_src.execute("SELECT COUNT(*) FROM vec_knowledge_rowids").fetchone()[0]
        dst_vec = conn_dst.execute("SELECT COUNT(*) FROM vec_knowledge_rowids").fetchone()[0]
        if src_vec != dst_vec:
            raise AbortMigration(
                f"vec_knowledge_rowids count mismatch: source={src_vec} dest={dst_vec}"
            )
        log.info("vec_knowledge_rowids count matches: %d", dst_vec)
    finally:
        conn_src.close()
        conn_dst.close()

    log.info("dqiii8_knowledge.db created and verified")


def step7_retire_metrics_db() -> None:
    log.info("=== step 7: retire dqiii8_metrics.db (rename, no DROP) ===")
    dst = DB_DIR / "dqiii8_metrics.db.old"
    if dst.exists():
        raise AbortMigration(f"{dst} already exists — refusing to overwrite")
    DB_METRICS.rename(dst)
    for suffix in ("-wal", "-shm"):
        sidecar = DB_DIR / f"dqiii8_metrics.db{suffix}"
        if sidecar.exists():
            sidecar.rename(DB_DIR / f"dqiii8_metrics.db.old{suffix}")
    log.info("renamed dqiii8_metrics.db -> dqiii8_metrics.db.old")


def step9_vacuum_main() -> None:
    log.info("=== step 9: light VACUUM on dqiii8.db ===")
    conn = sqlite3.connect(str(DB_MAIN))
    try:
        conn.execute("VACUUM")
    finally:
        conn.close()


def step10_permissions() -> None:
    log.info("=== step 10: chmod 600 on dqiii8_knowledge.db ===")
    DB_KNOWLEDGE.chmod(0o600)
    log.info("permissions set: %s", oct(DB_KNOWLEDGE.stat().st_mode & 0o777))


def step11_restart_writers() -> None:
    log.info("=== step 11: restart writers ===")
    result = _sh(["systemctl", "start"] + WRITER_UNITS, check=False)
    if result.returncode != 0:
        log.error(
            "failed to restart one or more units — manual intervention required: %s\n%s",
            WRITER_UNITS, result.stderr,
        )
    else:
        log.info("restarted: %s", ", ".join(WRITER_UNITS))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--execute", action="store_true", help="run steps 1-7 (default: dry-run only)")
    parser.add_argument(
        "--resume-after-code-fixes", action="store_true",
        help="run steps 9-11 (step 8, the code path fixes, must already be committed)",
    )
    args = parser.parse_args()

    if args.resume_after_code_fixes:
        if not args.execute:
            print("--resume-after-code-fixes requires --execute", file=sys.stderr)
            return 2
        try:
            step9_vacuum_main()
            step10_permissions()
        finally:
            step11_restart_writers()
        log.info("=== resumed migration complete ===")
        return 0

    step0_dry_run()

    if not args.execute:
        log.info("dry-run only (pass --execute to run steps 1-7). No changes made.")
        return 0

    writers_stopped = False
    reached_step7 = False
    try:
        step1_backup()
        step2_integrity_check()
        step3_stop_writers()
        writers_stopped = True
        step4_metrics_integrity_check()
        step5_transfer_session_memory()
        step6_create_knowledge_db()
        step7_retire_metrics_db()
        reached_step7 = True
        log.info(
            "=== steps 1-7 complete. STOP HERE. Writers remain stopped. ==="
            "\nApply the code path fixes now (11 modules + working_memory.py + "
            "6 infra files, see the plan) as a separate commit, with services "
            "still stopped. Then re-run with --execute --resume-after-code-fixes "
            "to VACUUM, fix permissions, and restart writers."
        )
        return 0
    except AbortMigration as exc:
        log.error("migration aborted: %s", exc)
        log.error("DBs are unchanged, or restorable from step 1's backup")
        return 1
    except Exception:
        log.exception("unexpected failure during migration")
        return 1
    finally:
        # Steps 1-7 succeeding is the ONLY path that should leave writers
        # down (by design, until the code-fix commit lands and
        # --resume-after-code-fixes runs step 11). Any abort or exception
        # above must restart immediately rather than leave production
        # silently offline waiting for a resume that may never come.
        if writers_stopped and not reached_step7:
            step11_restart_writers()


if __name__ == "__main__":
    sys.exit(main())
