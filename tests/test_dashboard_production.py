"""tests/test_dashboard_production.py — GET /api/production."""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

JARVIS = Path("/root/dqiii8/.claude/worktrees/dashboard-production-tracking-v2")


@pytest.fixture
def client(tmp_path, monkeypatch):
    (tmp_path / "database").mkdir(parents=True, exist_ok=True)
    real_db_path = tmp_path / "database" / "dqiii8.db"
    subprocess.run(
        ["sqlite3", str(real_db_path)],
        input=(JARVIS / "database" / "schema_v2.sql").read_text(),
        text=True,
        check=True,
    )
    # A project the /api/production endpoint should recognize as "known" —
    # it scans DQIII8_ROOT/my-projects/*/ for directory names, so without
    # this the endpoint sees zero known projects and every human_hours row
    # gets misclassified as "orphan", silently passing the orphan test for
    # the wrong reason.
    (tmp_path / "my-projects" / "intl-reports").mkdir(parents=True)

    monkeypatch.setenv("DQIII8_ROOT", str(tmp_path))
    # dashboard.py reads DQIII8_DASHBOARD_HOST (not DASHBOARD_HOST) to decide
    # REQUIRE_AUTH — confirmed at dashboard.py:47,49. Getting this name wrong
    # makes every request 401 only when the real env var happens to already
    # be set (e.g. under the systemd service), so it's a silent flake, not a
    # reliable local failure — get the name right rather than relying on luck.
    monkeypatch.setenv("DQIII8_DASHBOARD_HOST", "127.0.0.1")

    sys.path.insert(0, str(JARVIS / "bin" / "ui"))
    # dashboard.py's own sys.path bootstrap uses DQIII8_ROOT (now tmp_path,
    # for DB isolation) to locate bin/core, so the real bin/core/db.py
    # wouldn't be found via that logic in this test. Add the real repo's
    # bin/core explicitly so "from db import get_db" resolves to actual code.
    sys.path.insert(0, str(JARVIS / "bin" / "core"))
    # Both dashboard.py AND bin/core/db.py compute their DB path from
    # DQIII8_ROOT at import time (db.py's get_db() reads a module-level
    # DB_PATH set once on import) — popping only "dashboard" from
    # sys.modules leaves a stale db.DB_PATH pointing at the real production
    # DB if anything imported it earlier in the pytest session. Pop both.
    for _mod_name in ("dashboard", "db", "dashboard_security"):
        sys.modules.pop(_mod_name, None)
    import dashboard as dash_module

    conn = __import__("sqlite3").connect(str(real_db_path))
    conn.execute(
        "INSERT INTO agent_actions "
        "(session_id, agent_name, tool_used, action_type, estimated_cost_usd, "
        "duration_ms, success, project, timestamp) "
        "VALUES ('s1','agent','tool','api_call',0.05,1000,1,'intl-reports',datetime('now'))"
    )
    conn.execute(
        "INSERT INTO human_hours (project, started_at, ended_at, source) "
        "VALUES ('intl-reports', datetime('now','-1 hour'), datetime('now'), 'manual')"
    )
    conn.execute(
        "INSERT INTO human_hours (project, started_at, ended_at, source) "
        "VALUES ('orphan-typo', datetime('now','-1 hour'), datetime('now'), 'manual')"
    )
    conn.commit()
    conn.close()

    with TestClient(dash_module.app) as tc:
        yield tc


def test_production_endpoint_returns_project_metrics(client):
    resp = client.get("/api/production")
    assert resp.status_code == 200
    data = resp.json()
    assert "intl-reports" in data["projects"]
    proj = data["projects"]["intl-reports"]
    assert proj["agent"]["actions"] == 1
    assert proj["agent"]["cost_usd"] == pytest.approx(0.05)
    assert proj["human"]["minutes"] == pytest.approx(60, abs=1)


def test_production_endpoint_surfaces_orphan_projects(client):
    resp = client.get("/api/production")
    data = resp.json()
    assert "orphan-typo" in data["unrecognized_human_projects"]
