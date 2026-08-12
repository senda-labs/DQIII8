"""tests/test_project_context.py — resolve_project()/set_project() precedence and contract."""
import sqlite3
import subprocess
import sys
from pathlib import Path

JARVIS = Path(__file__).parent.parent
sys.path.insert(0, str(JARVIS))

import bin.core.project_context as pc  # noqa: E402


def _fresh_db(tmp_path):
    db_path = tmp_path / "dqiii8.db"
    subprocess.run(
        ["sqlite3", str(db_path)],
        input=(JARVIS / "database" / "schema_v2.sql").read_text(),
        text=True,
        check=True,
    )
    return db_path


def _patch_db(monkeypatch, db_path):
    monkeypatch.setattr(pc, "DB_PATH", db_path)


def test_explicit_project_arg_wins(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    assert pc.resolve_project(project="football-value", session_id="whatever") == "football-value"


def test_session_scoped_row_beats_global_row(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO project_context (scope, project, declared_at, declared_by) "
        "VALUES ('global', 'dqiii8-core', '2026-08-13 09:00:00', 'cli')"
    )
    conn.execute(
        "INSERT INTO project_context (scope, project, declared_at, declared_by) "
        "VALUES ('sess-123', 'intl-reports', '2026-08-13 09:00:00', 'session_start')"
    )
    conn.commit()
    conn.close()
    assert pc.resolve_project(session_id="sess-123") == "intl-reports"


def test_global_row_used_when_no_session_row(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO project_context (scope, project, declared_at, declared_by) "
        "VALUES ('global', 'intl-reports', '2026-08-13 09:00:00', 'cli')"
    )
    conn.commit()
    conn.close()
    assert pc.resolve_project(session_id="sess-no-row") == "intl-reports"


def test_cwd_fallback_requires_known_project(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    monkeypatch.setattr(pc, "MY_PROJECTS_DIR", tmp_path / "my-projects")
    (tmp_path / "my-projects" / "football-value").mkdir(parents=True)
    assert pc.resolve_project(cwd="/root/dqiii8/my-projects/football-value/scripts") == "football-value"


def test_cwd_fallback_rejects_unknown_slug(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    monkeypatch.setattr(pc, "MY_PROJECTS_DIR", tmp_path / "my-projects")
    (tmp_path / "my-projects").mkdir(parents=True)
    assert pc.resolve_project(cwd="/root/dqiii8/my-projects/typo-project/scripts") == pc.CORE_PROJECT


def test_no_signal_defaults_to_core(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    monkeypatch.setattr(pc, "MY_PROJECTS_DIR", tmp_path / "my-projects")
    assert pc.resolve_project(cwd="/root/dqiii8") == pc.CORE_PROJECT


def test_db_error_fails_open_to_cwd_default(monkeypatch, tmp_path):
    _patch_db(monkeypatch, tmp_path / "does-not-exist.db")
    monkeypatch.setattr(pc, "MY_PROJECTS_DIR", tmp_path / "my-projects")
    assert pc.resolve_project(session_id="sess-1", cwd="/root/dqiii8") == pc.CORE_PROJECT


def test_set_project_rejects_unknown_project(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    monkeypatch.setattr(pc, "MY_PROJECTS_DIR", tmp_path / "my-projects")
    try:
        pc.set_project("not-a-real-project", scope="global", declared_by="cli")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_set_project_rejects_unknown_declared_by(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    try:
        pc.set_project("dqiii8-core", scope="global", declared_by="carrier_pigeon")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_set_project_then_get_project_round_trip(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    pc.set_project("dqiii8-core", scope="global", declared_by="cli")
    assert pc.get_project("global") == "dqiii8-core"


def test_set_project_closes_prior_open_row(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    pc.set_project("dqiii8-core", scope="global", declared_by="cli")
    pc.set_project("football-value", scope="global", declared_by="cli")
    conn = sqlite3.connect(str(db_path))
    open_rows = conn.execute(
        "SELECT project FROM project_context WHERE scope='global' AND ended_at IS NULL"
    ).fetchall()
    conn.close()
    assert open_rows == [("football-value",)]


def test_end_project_closes_open_row(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    pc.set_project("dqiii8-core", scope="global", declared_by="cli")
    assert pc.end_project("global") is True
    assert pc.get_project("global") is None


def test_end_project_no_open_row_returns_false(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    assert pc.end_project("global") is False


def test_known_projects_includes_core_and_my_projects_dirs(monkeypatch, tmp_path):
    monkeypatch.setattr(pc, "MY_PROJECTS_DIR", tmp_path / "my-projects")
    (tmp_path / "my-projects" / "football-value").mkdir(parents=True)
    (tmp_path / "my-projects" / "intl-reports").mkdir(parents=True)
    assert pc.known_projects() == {"dqiii8-core", "football-value", "intl-reports"}


def test_known_projects_fails_open_when_dir_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(pc, "MY_PROJECTS_DIR", tmp_path / "no-such-dir")
    assert pc.known_projects() == {"dqiii8-core"}
