"""tests/test_human_hours_schema.py — human_hours table contract."""
import sqlite3
import subprocess
import sys
from pathlib import Path

JARVIS = Path(__file__).parent.parent  # current worktree or repo root


def _fresh_db(tmp_path):
    db_path = tmp_path / "dqiii8.db"
    subprocess.run(
        ["sqlite3", str(db_path)],
        input=(JARVIS / "database" / "schema_v2.sql").read_text(),
        text=True,
        check=True,
    )
    return db_path


def test_human_hours_table_exists(tmp_path):
    db_path = _fresh_db(tmp_path)
    conn = sqlite3.connect(str(db_path))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(human_hours)").fetchall()}
    conn.close()
    assert cols == {"id", "project", "started_at", "ended_at", "note", "source"}


def test_human_hours_source_check_rejects_invalid(tmp_path):
    db_path = _fresh_db(tmp_path)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO human_hours (project, started_at, source) VALUES (?, ?, ?)",
            ("intl-reports", "2026-08-11T10:00:00", "carrier_pigeon"),
        )
        conn.commit()
        assert False, "expected CHECK constraint violation"
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()


def test_human_hours_prevents_duplicate_open_session(tmp_path):
    db_path = _fresh_db(tmp_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO human_hours (project, started_at, source) VALUES (?, ?, 'manual')",
        ("intl-reports", "2026-08-11T10:00:00"),
    )
    conn.commit()
    try:
        conn.execute(
            "INSERT INTO human_hours (project, started_at, source) VALUES (?, ?, 'manual')",
            ("intl-reports", "2026-08-11T11:00:00"),
        )
        conn.commit()
        assert False, "expected unique-open-session violation"
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()


def test_human_hours_allows_second_open_after_first_closed(tmp_path):
    db_path = _fresh_db(tmp_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO human_hours (project, started_at, source) VALUES (?, ?, 'manual')",
        ("intl-reports", "2026-08-11T10:00:00"),
    )
    conn.commit()
    conn.execute(
        "UPDATE human_hours SET ended_at = ? WHERE project = 'intl-reports' AND ended_at IS NULL",
        ("2026-08-11T12:00:00",),
    )
    conn.commit()
    conn.execute(
        "INSERT INTO human_hours (project, started_at, source) VALUES (?, ?, 'manual')",
        ("intl-reports", "2026-08-11T13:00:00"),
    )
    conn.commit()
    count = conn.execute(
        "SELECT COUNT(*) FROM human_hours WHERE project = 'intl-reports'"
    ).fetchone()[0]
    conn.close()
    assert count == 2
