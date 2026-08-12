"""tests/test_project_value_and_roi.py — Stage 8 (ROI/Tiempos/Costes/Performance) contract.

See /root/.claude/plans/distributed-wobbling-gem.md for the design rationale.
"""
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


def _insert_action(conn, project, timestamp, tool_used="Edit", file_path="foo.py",
                    session_id="sess-1", duration_ms=3_600_000, agent_name="test-agent"):
    conn.execute(
        "INSERT INTO agent_actions (project, timestamp, agent_name, tool_used, file_path, session_id, "
        "start_time_ms, end_time_ms, duration_ms, success) "
        "VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, 1)",
        (project, timestamp, agent_name, tool_used, file_path, session_id, duration_ms, duration_ms),
    )


def _insert_human_hours(conn, project, started_at, ended_at):
    conn.execute(
        "INSERT INTO human_hours (project, started_at, ended_at, source) VALUES (?, ?, ?, 'manual')",
        (project, started_at, ended_at),
    )


def test_record_project_value_rejects_unknown_project(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    monkeypatch.setattr(pc, "MY_PROJECTS_DIR", tmp_path / "my-projects")
    try:
        pc.record_project_value("not-a-real-project", "fee_cobrado", 100.0)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_record_project_value_rejects_invalid_tipo(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    try:
        pc.record_project_value("dqiii8-core", "not-a-real-tipo", 100.0)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_record_project_value_inserts_row(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    pc.record_project_value("dqiii8-core", "fee_cobrado", 500.0, nota="test")
    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT project, tipo, importe_eur, nota FROM project_value").fetchone()
    conn.close()
    assert row == ("dqiii8-core", "fee_cobrado", 500.0, "test")


def test_v_project_roi_empty_when_no_project_value_rows(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    assert pc.get_project_roi() == []


def test_v_project_roi_nonzero_after_fee_cobrado_insert(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    pc.set_labor_rate(35.0)
    pc.record_project_value("dqiii8-core", "fee_cobrado", 1000.0)
    rows = pc.get_project_roi("dqiii8-core")
    assert len(rows) == 1
    assert rows[0]["ingresos_eur"] == 1000.0
    assert rows[0]["roi_eur"] == 1000.0


def test_v_project_roi_ignores_valor_estimado_in_ingresos(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    pc.record_project_value("dqiii8-core", "valor_estimado", 5000.0)
    rows = pc.get_project_roi("dqiii8-core")
    assert rows[0]["ingresos_eur"] == 0.0


def test_set_project_status_rejects_invalid_status(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    try:
        pc.set_project_status("dqiii8-core", "not-a-real-status")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_set_project_status_updates_open_row_only(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    pc.set_project("dqiii8-core", scope="global", declared_by="cli")
    pc.end_project("global")
    pc.set_project("dqiii8-core", scope="global", declared_by="cli")
    pc.set_project_status("dqiii8-core", "pausado")
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT status, ended_at FROM project_context WHERE project='dqiii8-core' ORDER BY id"
    ).fetchall()
    conn.close()
    assert rows[0][0] == "activo"
    assert rows[0][1] is not None
    assert rows[1][0] == "pausado"
    assert rows[1][1] is None


def test_set_project_status_then_get_project_status_round_trip(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    pc.set_project("dqiii8-core", scope="global", declared_by="cli")
    pc.set_project_status("dqiii8-core", "entregado")
    assert pc.get_project_status("dqiii8-core") == "entregado"


def test_set_project_budget_upserts(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    pc.set_project_budget("dqiii8-core", 1000.0)
    pc.set_project_budget("dqiii8-core", 2000.0)
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("SELECT presupuesto_eur FROM project_budget WHERE project='dqiii8-core'").fetchall()
    conn.close()
    assert rows == [(2000.0,)]


def test_v_budget_deviation_pct_positive_when_over_budget(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    pc.set_labor_rate(35.0)
    conn = sqlite3.connect(str(db_path))
    _insert_action(conn, "dqiii8-core", "2026-08-13 09:00:00")
    _insert_human_hours(conn, "dqiii8-core", "2026-08-13 09:00:00", "2026-08-13 19:00:00")  # 10h
    conn.commit()
    conn.close()
    pc.set_project_budget("dqiii8-core", 10.0)  # tiny budget -> way over
    rows = pc.get_budget_status("dqiii8-core")
    assert rows[0]["desviacion_pct"] > 0


def test_v_budget_deviation_pct_negative_when_under_budget(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    pc.set_labor_rate(35.0)
    conn = sqlite3.connect(str(db_path))
    _insert_action(conn, "dqiii8-core", "2026-08-13 09:00:00")
    _insert_human_hours(conn, "dqiii8-core", "2026-08-13 09:00:00", "2026-08-13 10:00:00")  # 1h
    conn.commit()
    conn.close()
    pc.set_project_budget("dqiii8-core", 1_000_000.0)
    rows = pc.get_budget_status("dqiii8-core")
    assert rows[0]["desviacion_pct"] < 0


def test_v_context_fragmentation_computes_mean_max_gap(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    conn = sqlite3.connect(str(db_path))
    _insert_action(conn, "dqiii8-core", "2026-08-13 09:00:00", session_id="sess-1")
    _insert_action(conn, "dqiii8-core", "2026-08-13 09:10:00", session_id="sess-1")
    _insert_action(conn, "dqiii8-core", "2026-08-13 09:40:00", session_id="sess-1")
    conn.commit()
    row = conn.execute(
        "SELECT gap_samples, mean_gap_s, max_gap_s FROM v_context_fragmentation WHERE project='dqiii8-core'"
    ).fetchone()
    conn.close()
    assert row[0] == 2
    assert row[1] == 1200.0
    assert row[2] == 1800.0


def test_v_infra_cost_weekly_allocates_proportionally_by_agent_hours(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO infra_costs (item, importe_eur_mes) VALUES ('test-infra', 43.45)"
    )
    _insert_action(conn, "dqiii8-core", "2026-08-13 09:00:00", duration_ms=3_600_000)  # 1h
    _insert_action(conn, "football-value", "2026-08-13 09:00:00", duration_ms=3_600_000 * 3)  # 3h
    conn.commit()
    rows = conn.execute(
        "SELECT project, infra_cost_eur FROM v_infra_cost_weekly ORDER BY project"
    ).fetchall()
    conn.close()
    by_project = dict(rows)
    total = sum(by_project.values())
    weekly_pool = round(43.45 / 4.345, 4)
    assert abs(total - weekly_pool) < 0.01
    assert by_project["football-value"] > by_project["dqiii8-core"]


def test_v_rework_signal_detects_reedit_within_24h(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    conn = sqlite3.connect(str(db_path))
    _insert_action(conn, "dqiii8-core", "2026-08-13 09:00:00", file_path="foo.py")
    _insert_action(conn, "dqiii8-core", "2026-08-13 15:00:00", file_path="foo.py")
    conn.commit()
    rows = conn.execute("SELECT hours_between FROM v_rework_signal").fetchall()
    conn.close()
    assert rows == [(6.0,)]


def test_v_rework_signal_excludes_reedit_outside_24h(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    conn = sqlite3.connect(str(db_path))
    _insert_action(conn, "dqiii8-core", "2026-08-13 09:00:00", file_path="foo.py")
    _insert_action(conn, "dqiii8-core", "2026-08-15 09:00:01", file_path="foo.py")
    conn.commit()
    rows = conn.execute("SELECT hours_between FROM v_rework_signal").fetchall()
    conn.close()
    assert rows == []


def test_v_rework_signal_excludes_rows_with_null_file_path(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    conn = sqlite3.connect(str(db_path))
    _insert_action(conn, "dqiii8-core", "2026-08-13 09:00:00", file_path=None)
    _insert_action(conn, "dqiii8-core", "2026-08-13 10:00:00", file_path=None)
    conn.commit()
    rows = conn.execute("SELECT hours_between FROM v_rework_signal").fetchall()
    conn.close()
    assert rows == []


def test_set_labor_rate_rejects_non_positive(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    try:
        pc.set_labor_rate(0.0)
        assert False, "expected ValueError"
    except ValueError:
        pass
    try:
        pc.set_labor_rate(-5.0)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_set_labor_rate_then_get_labor_rate_round_trip(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    pc.set_labor_rate(50.0, basis="test override")
    assert pc.get_labor_rate() == 50.0


def test_v_project_roi_coste_humano_reflects_latest_labor_rate(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    conn = sqlite3.connect(str(db_path))
    _insert_action(conn, "dqiii8-core", "2026-08-13 09:00:00")
    _insert_human_hours(conn, "dqiii8-core", "2026-08-13 09:00:00", "2026-08-13 10:00:00")  # 1h
    conn.execute(
        "INSERT INTO labor_rates (rate_eur_hour, basis, effective_date) VALUES (50.0, 'newer', '2026-08-20')"
    )
    conn.commit()
    conn.close()
    pc.record_project_value("dqiii8-core", "fee_cobrado", 1000.0)
    rows = pc.get_project_roi("dqiii8-core")
    assert rows[0]["coste_humano_eur"] == 50.0


def test_v_rework_signal_literal_matches_rework_window_constant(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='view' AND name='v_rework_signal'"
    ).fetchone()
    conn.close()
    assert f"<= {pc.REWORK_WINDOW_HOURS}" in row[0]


# Regression tests for the /panel-review Opus findings (2026-08-12), fixed same-day:

def test_v_project_roi_counts_human_hours_week_with_no_agent_actions(monkeypatch, tmp_path):
    # P1: v_project_cost_weekly (FROM agent_agg LEFT JOIN human_agg) drops any
    # week with human_hours but zero agent_actions. v_project_roi must not
    # inherit that drop — it sums human_hours directly.
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    pc.set_labor_rate(35.0)
    conn = sqlite3.connect(str(db_path))
    _insert_human_hours(conn, "dqiii8-core", "2026-08-10 09:00:00", "2026-08-10 12:00:00")  # 3h, no agent_actions
    conn.commit()
    conn.close()
    rows = pc.get_project_roi("dqiii8-core")
    assert len(rows) == 1
    assert rows[0]["human_hours"] == 3.0
    assert rows[0]["coste_humano_eur"] == 105.0


def test_v_budget_deviation_counts_human_hours_week_with_no_agent_actions(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    pc.set_labor_rate(35.0)
    pc.set_project_budget("dqiii8-core", 100.0)
    conn = sqlite3.connect(str(db_path))
    _insert_human_hours(conn, "dqiii8-core", "2026-08-10 09:00:00", "2026-08-10 12:00:00")  # 3h, no agent_actions
    conn.commit()
    conn.close()
    rows = pc.get_budget_status("dqiii8-core")
    assert len(rows) == 1
    assert rows[0]["human_hours"] == 3.0
    assert rows[0]["coste_humano_eur"] == 105.0


def test_v_project_roi_includes_project_with_costs_but_no_value(monkeypatch, tmp_path):
    # P2: a project with real costs but no project_value row must still
    # surface (ingresos_eur=0), not be invisible to ROI reporting.
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    pc.set_labor_rate(35.0)
    conn = sqlite3.connect(str(db_path))
    _insert_human_hours(conn, "dqiii8-core", "2026-08-10 09:00:00", "2026-08-10 11:00:00")  # 2h
    conn.commit()
    conn.close()
    rows = pc.get_project_roi("dqiii8-core")
    assert len(rows) == 1
    assert rows[0]["ingresos_eur"] == 0.0
    assert rows[0]["human_hours"] == 2.0
    assert rows[0]["coste_humano_eur"] == 70.0
    assert rows[0]["roi_eur"] == -70.0


def test_set_project_status_terminal_after_project_already_ended(monkeypatch, tmp_path):
    # P2: setting a terminal status after end_project() already closed the
    # row must not silently affect 0 rows.
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    pc.set_project("dqiii8-core", scope="global", declared_by="cli")
    pc.end_project("global")
    pc.set_project_status("dqiii8-core", "entregado")
    assert pc.get_project_status("dqiii8-core") == "entregado"
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT status FROM project_context WHERE project='dqiii8-core' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row[0] == "entregado"


def test_set_project_status_raises_when_no_context_row_exists(monkeypatch, tmp_path):
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    try:
        pc.set_project_status("dqiii8-core", "entregado")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_v_infra_cost_weekly_zero_not_null_when_infra_costs_empty(monkeypatch, tmp_path):
    # Disaster scenario: every infra_costs row retired (or none ever seeded).
    # weekly_pool's SUM() over zero rows is NULL — without a COALESCE guard
    # that NULL propagates through the multiplication to infra_cost_eur,
    # silently breaking downstream SUM()s in v_project_roi/v_budget_deviation.
    db_path = _fresh_db(tmp_path)
    _patch_db(monkeypatch, db_path)
    conn = sqlite3.connect(str(db_path))
    _insert_action(conn, "dqiii8-core", "2026-08-13 09:00:00", duration_ms=3_600_000)
    conn.commit()
    rows = conn.execute("SELECT infra_cost_eur FROM v_infra_cost_weekly").fetchall()
    conn.close()
    assert rows == [(0.0,)]
