#!/usr/bin/env python3
"""Shared database connection manager for DQIII8.
All modules should use get_db() instead of opening connections manually."""
import sqlite3
import os
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8")) / "database" / "dqiii8.db"


@contextmanager
def get_db(timeout=10):
    """Context manager for SQLite connections. Auto-commits on success, rollbacks on error."""
    conn = sqlite3.connect(str(DB_PATH), timeout=timeout)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query(sql: str, params=(), fetchone=False):
    """Quick query helper for simple reads."""
    with get_db() as conn:
        cursor = conn.execute(sql, params)
        return cursor.fetchone() if fetchone else cursor.fetchall()


def execute(sql: str, params=()):
    """Quick execute helper for writes."""
    with get_db() as conn:
        conn.execute(sql, params)
