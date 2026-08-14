#!/usr/bin/env python3
"""One-time DB consolidation: fold dqiii8_metrics.db -> dqiii8_knowledge.db,
migrate session_memory from dqiii8_history.db into dqiii8.db.

Implements docs/superpowers/specs/2026-08-14-db-consolidation-design.md §5.3
and /root/.claude/plans/resilient-snuggling-parrot.md. Idempotent guard: exits
early if dqiii8_knowledge.db already exists.

Run from a non-Claude-Code shell (SSH/tmux) so pre_tool_use.py/post_tool_use.py
hooks don't write to agent_actions/error_log/vault_memory during the
"no writers" window.
"""
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DB_DIR = ROOT / "database"
DB_OPS = DB_DIR / "dqiii8.db"
DB_HISTORY = DB_DIR / "dqiii8_history.db"
DB_METRICS = DB_DIR / "dqiii8_metrics.db"
DB_KNOWLEDGE = DB_DIR / "dqiii8_knowledge.db"
SCHEMA = DB_DIR / "schema_v2.sql"

UNITS = ["dqiii8-bot", "dq-dashboard", "cron", "hpt-poller.timer", "dqiii8-health.timer"]


def sh(*args, check=True):
    return subprocess.run(args, capture_output=True, text=True, check=check)


def integrity_ok(path):
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    ok = conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()
    return ok


def step0_dry_run():
    print("[0] dry-run checks")
    if DB_KNOWLEDGE.exists():
        print("dqiii8_knowledge.db already exists — aborting (idempotent guard).")
        sys.exit(0)
    for db in (DB_OPS, DB_HISTORY, DB_METRICS):
        assert integrity_ok(db), f"integrity_check failed for {db}"
    # Precondition (unrelated dirty work) was cleaned separately before this
    # script existed (see plan §"Precondición") — any diff present now is this
    # migration's own in-progress code (this script + the DB_PATH refactor),
    # which lands in the same commit as step 8, so it's expected here.
    print("  dry-run OK")


def step1_backup():
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bdir = DB_DIR / "backups" / f"pre-consolidation-{ts}"
    bdir.mkdir(parents=True, exist_ok=True)
    for db in (DB_OPS, DB_HISTORY, DB_METRICS):
        shutil.copy2(db, bdir / db.name)
    print(f"[1] backup -> {bdir}")
    return bdir


def step3_stop_units():
    print("[3] stopping writers:", UNITS)
    sh("systemctl", "stop", *UNITS)


def step11_restart_units():
    print("[11] restarting writers")
    sh("systemctl", "start", *UNITS)


def step4_metrics_integrity():
    assert integrity_ok(DB_METRICS), "metrics.db integrity_check failed pre-copy"
    print("[4] metrics.db integrity OK immediately pre-copy")


def step5_session_memory():
    print("[5] session_memory migration")
    conn_h = sqlite3.connect(f"file:{DB_HISTORY}?mode=ro", uri=True)
    frozen_count = conn_h.execute("SELECT COUNT(*) FROM session_memory").fetchone()[0]
    create_sql = conn_h.execute(
        "SELECT sql FROM sqlite_master WHERE name='session_memory'"
    ).fetchone()[0]
    conn_h.close()

    if "session_memory" not in SCHEMA.read_text():
        with SCHEMA.open("a") as f:
            f.write("\n\n-- Added 2026-08-14: DB consolidation (session_memory from dqiii8_history.db)\n")
            f.write(create_sql.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS", 1) + ";\n")
        print("  schema_v2.sql updated")

    sh("sqlite3", str(DB_OPS), f".read {SCHEMA}")

    conn = sqlite3.connect(DB_OPS)
    conn.execute(f"ATTACH DATABASE '{DB_HISTORY}' AS history")
    conn.execute(
        "INSERT OR IGNORE INTO session_memory (id, session_id, role, content, domain, timestamp) "
        "SELECT id, session_id, role, content, domain, timestamp FROM history.session_memory"
    )
    conn.commit()
    migrated_count = conn.execute("SELECT COUNT(*) FROM session_memory").fetchone()[0]
    conn.execute("DETACH DATABASE history")
    conn.close()

    assert migrated_count == frozen_count, (
        f"session_memory count mismatch: history={frozen_count} dqiii8.db={migrated_count}"
    )
    print(f"  migrated {migrated_count} rows, verified against frozen count")


def step6_create_knowledge_db():
    print("[6] creating dqiii8_knowledge.db via .backup")
    sh("sqlite3", str(DB_METRICS), f".backup {DB_KNOWLEDGE}")
    assert integrity_ok(DB_KNOWLEDGE), "dqiii8_knowledge.db integrity_check failed"

    conn_m = sqlite3.connect(f"file:{DB_METRICS}?mode=ro", uri=True)
    src_count = conn_m.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type IN ('table','view')"
    ).fetchone()[0]
    conn_m.close()

    conn_k = sqlite3.connect(f"file:{DB_KNOWLEDGE}?mode=ro", uri=True)
    dst_count = conn_k.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type IN ('table','view')"
    ).fetchone()[0]
    vec_rows = conn_k.execute("SELECT COUNT(*) FROM vec_knowledge_rowids").fetchone()[0]
    conn_k.close()

    assert src_count == dst_count, f"table/view count mismatch: {src_count} vs {dst_count}"
    assert vec_rows > 0, "vec_knowledge_rowids empty in new DB"
    print(f"  {dst_count} tables+views, {vec_rows} vec_knowledge_rowids rows verified")


def step7_retire_metrics():
    old = DB_METRICS.with_suffix(".db.old")
    DB_METRICS.rename(old)
    print(f"[7] {DB_METRICS.name} -> {old.name}")


def step9_vacuum():
    print("[9] vacuum dqiii8.db")
    sh("sqlite3", str(DB_OPS), "PRAGMA busy_timeout=5000; VACUUM;")


def step10_chmod():
    DB_KNOWLEDGE.chmod(0o600)
    print("[10] chmod 600 dqiii8_knowledge.db")


def main():
    step0_dry_run()
    step1_backup()
    step3_stop_units()
    try:
        step4_metrics_integrity()
        step5_session_memory()
        step6_create_knowledge_db()
        step7_retire_metrics()
        step9_vacuum()
        step10_chmod()
    finally:
        step11_restart_units()
    print("\nConsolidation complete. dqiii8_metrics.db.old kept as a ~72h safety buffer.")


if __name__ == "__main__":
    main()
