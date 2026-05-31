#!/usr/bin/env python3
"""Idempotent DB initializer — applies schema_v2.sql if dqiii8.db is absent or empty.

Usage:
    python3 -m bin.tools.db_init          # default paths via DQIII8_ROOT
    python3 bin/tools/db_init.py          # same
    python3 bin/tools/db_init.py --check  # verify tables only, no writes
"""
import argparse
import logging
import sqlite3
import sys
from pathlib import Path

try:
    from bin.core.paths import DB_PATH, SCHEMA_PATH
except ImportError:
    _root = Path(__file__).resolve().parents[2]
    DB_PATH = _root / "database" / "dqiii8.db"
    SCHEMA_PATH = _root / "database" / "schema_v2.sql"

_log = logging.getLogger("dqiii8.db_init")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

MIGRATIONS_DIR = SCHEMA_PATH.parent / "migrations"


def _table_count(conn: sqlite3.Connection) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
    ).fetchone()[0]


def init_db(db_path: Path = DB_PATH, schema_path: Path = SCHEMA_PATH) -> None:
    if not schema_path.exists():
        _log.error("Schema not found: %s", schema_path)
        sys.exit(1)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema_sql = schema_path.read_text(encoding="utf-8")

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        before = _table_count(conn)
        conn.executescript(schema_sql)
        conn.commit()
        after = _table_count(conn)
        if after > before:
            _log.info("DB initialized: %s  (%d → %d tables)", db_path, before, after)
        else:
            _log.info("DB already up to date: %s  (%d tables)", db_path, after)

        # Apply any migration files (currently none — directory is empty)
        if MIGRATIONS_DIR.is_dir():
            for mig in sorted(MIGRATIONS_DIR.glob("*.sql")):
                _log.info("Applying migration: %s", mig.name)
                conn.executescript(mig.read_text(encoding="utf-8"))
                conn.commit()
    finally:
        conn.close()


def check_db(db_path: Path = DB_PATH) -> bool:
    if not db_path.exists():
        _log.warning("DB absent: %s", db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=5)
    try:
        n = _table_count(conn)
        _log.info("DB OK: %s  (%d tables)", db_path, n)
        return n > 0
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DQIII8 DB initializer")
    parser.add_argument("--check", action="store_true", help="Verify tables only, no writes")
    parser.add_argument("--db", default=str(DB_PATH), help="DB path override")
    parser.add_argument("--schema", default=str(SCHEMA_PATH), help="Schema path override")
    args = parser.parse_args()

    if args.check:
        ok = check_db(Path(args.db))
        sys.exit(0 if ok else 1)
    else:
        init_db(Path(args.db), Path(args.schema))
