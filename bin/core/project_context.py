#!/usr/bin/env python3
"""Project SSOT — single resolver for "which project is this action for".

Replaces the two dead file-glob resolvers in session_start.py and
user_prompt_submit.py (both targeted /root/dqiii8/projects/, which does not
exist — Correction C) and the ad-hoc cwd-sniffing duplicated across
pre_tool_use.py, openrouter_wrapper.py and pal/engine.py.

Precedence:
  1. explicit `project=` arg from the caller
  2. open project_context row for this session_id
  3. open project_context row for scope='global' (the user's declaration)
  4. cwd match on /my-projects/<x>/ (preserves pre_tool_use.py's prior behavior)
  5. literal 'dqiii8-core' (matches session_start.py/post_tool_use.py's
     existing hardcoded fallback — project can never be NULL on a new row)

A DQIII8_PROJECT env var was tried as a process-local cache to skip the DB
round-trip on the hot pre_tool_use.py path (Correction I.1), then removed
post-Stage-7 (Opus adversarial review P2-5): each Claude Code hook fires as
its own fresh subprocess, not a parent of the next hook's process, so nothing
one hook writes to os.environ is ever visible to another — the env var was
silently dead code, never actually read back. A real fix would need a
cross-process cache (e.g. a file keyed by session_id), which is deferred as
a separate, deliberately-scoped change rather than added under this review.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DQIII8_ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
DB_PATH = DQIII8_ROOT / "database" / "dqiii8.db"
MY_PROJECTS_DIR = DQIII8_ROOT / "my-projects"
CORE_PROJECT = "dqiii8-core"

_VALID_DECLARED_BY = {"telegram", "cli", "session_start", "prompt", "api"}


def known_projects() -> set[str]:
    """Validated project name universe: my-projects/<slug> dirs + dqiii8-core."""
    if not MY_PROJECTS_DIR.exists():
        return {CORE_PROJECT}
    return {p.name for p in MY_PROJECTS_DIR.iterdir() if p.is_dir()} | {CORE_PROJECT}


def _open_context_row(scope: str, timeout: float) -> str | None:
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(DB_PATH), timeout=timeout)
    try:
        row = conn.execute(
            "SELECT project FROM project_context WHERE scope=? AND ended_at IS NULL "
            "ORDER BY declared_at DESC LIMIT 1",
            (scope,),
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def resolve_project(
    project: str | None = None,
    session_id: str | None = None,
    cwd: str | None = None,
    db_timeout: float = 2.0,
) -> str:
    """Resolve the project a caller's action should attribute to.

    Fails open on any DB error (steps 2/3): log at DEBUG, skip DB resolution,
    fall through to the cwd/default steps rather than blocking the hot INSERT
    path a caller is usually on (Stage 2 panel-pass-2 concern re: SQLITE_BUSY).
    """
    if project:
        return project

    if session_id:
        try:
            row = _open_context_row(session_id, db_timeout)
            if row:
                return row
        except Exception:
            pass

    try:
        row = _open_context_row("global", db_timeout)
        if row:
            return row
    except Exception:
        pass

    _cwd = cwd if cwd is not None else os.environ.get("PWD", "")
    marker = "/my-projects/"
    if marker in _cwd:
        rest = _cwd.split(marker, 1)[1]
        slug = rest.split("/", 1)[0]
        # Opus review P3-13: an unvalidated cwd slug (typo, stray dir under
        # my-projects/ with no PROJECT.md) would otherwise get written straight
        # to agent_actions.project, bypassing the validation set_project()
        # enforces. known_projects() already fails open to {CORE_PROJECT}.
        if slug and slug in known_projects():
            return slug

    return CORE_PROJECT


def set_project(
    project: str,
    scope: str,
    declared_by: str,
    source_detail: str | None = None,
    validate: bool = True,
) -> None:
    """Open a new project_context row for `scope`, closing any prior open row.

    Raises ValueError if `project` isn't a known project and validate=True.
    """
    if declared_by not in _VALID_DECLARED_BY:
        raise ValueError(f"declared_by must be one of {_VALID_DECLARED_BY}")
    if validate and project not in known_projects():
        raise ValueError(f"unknown project: {project!r}")

    import datetime as _dt

    # Stored in the same 'YYYY-MM-DD HH:MM:SS' shape as SQLite's own
    # datetime('now') (agent_actions.timestamp's default) — not
    # .isoformat()'s 'T'-separated/offset-suffixed form. schema_v2.sql's
    # v_action_project compares declared_at/ended_at against
    # agent_actions.timestamp as plain strings; at the 'T' vs ' ' byte the
    # ISO form always sorts after, so every same-day action was silently
    # falling through to 'unattributed' before this fix.
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        conn.execute(
            "UPDATE project_context SET ended_at=? WHERE scope=? AND ended_at IS NULL",
            (now, scope),
        )
        conn.execute(
            "INSERT INTO project_context (scope, project, declared_at, declared_by, source_detail) "
            "VALUES (?, ?, ?, ?, ?)",
            (scope, project, now, declared_by, source_detail),
        )
        conn.commit()
    finally:
        conn.close()


def end_project(scope: str) -> bool:
    """Close the open project_context row for `scope`. Returns True if a row was closed."""
    import datetime as _dt

    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        cur = conn.execute(
            "UPDATE project_context SET ended_at=? WHERE scope=? AND ended_at IS NULL",
            (now, scope),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_project(scope: str) -> str | None:
    """Return the currently open project for `scope`, or None if none is open."""
    return _open_context_row(scope, timeout=10)


# Stage 8 (ROI/Tiempos/Costes/Performance addendum, see
# /root/.claude/plans/distributed-wobbling-gem.md).

REWORK_WINDOW_HOURS = 24.0  # mirrors the hardcoded literal in v_rework_signal (SQL)

_VALID_VALUE_TIPO = {"fee_cobrado", "hito_entregado", "valor_estimado"}
_VALID_STATUS = {"activo", "pausado", "entregado", "abandonado"}


def record_project_value(
    project: str, tipo: str, importe_eur: float, nota: str | None = None
) -> None:
    """Insert a project_value row (revenue/milestone/estimate)."""
    if project not in known_projects():
        raise ValueError(f"unknown project: {project!r}")
    if tipo not in _VALID_VALUE_TIPO:
        raise ValueError(f"tipo must be one of {_VALID_VALUE_TIPO}")

    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        conn.execute(
            "INSERT INTO project_value (project, tipo, importe_eur, nota) VALUES (?, ?, ?, ?)",
            (project, tipo, importe_eur, nota),
        )
        conn.commit()
    finally:
        conn.close()


def set_project_status(project: str, status: str) -> None:
    """Set `status` on the open project_context row for `project` (ended_at IS NULL).

    Falls back to the most recent row (open or closed) when none is open:
    terminal statuses ('entregado'/'abandonado') are set precisely when a
    project is finished, by which point end_project() has usually already
    closed its row — without the fallback that update silently affects 0
    rows and reports success (Opus panel-review P2, 2026-08-12).
    """
    if project not in known_projects():
        raise ValueError(f"unknown project: {project!r}")
    if status not in _VALID_STATUS:
        raise ValueError(f"status must be one of {_VALID_STATUS}")

    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        cur = conn.execute(
            "UPDATE project_context SET status=? WHERE project=? AND ended_at IS NULL",
            (status, project),
        )
        if cur.rowcount == 0:
            cur = conn.execute(
                "UPDATE project_context SET status=? WHERE id = ("
                "  SELECT id FROM project_context WHERE project=? "
                "  ORDER BY declared_at DESC, id DESC LIMIT 1)",
                (status, project),
            )
        if cur.rowcount == 0:
            raise ValueError(f"no project_context row exists for {project!r}")
        conn.commit()
    finally:
        conn.close()


def get_project_status(project: str) -> str | None:
    """Return the status of the most recent project_context row for `project`, or None.

    Not filtered to ended_at IS NULL — mirrors set_project_status's fallback so a
    terminal status set on an already-closed row is still readable back.
    """
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        row = conn.execute(
            "SELECT status FROM project_context WHERE project=? "
            "ORDER BY declared_at DESC, id DESC LIMIT 1",
            (project,),
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def set_project_budget(project: str, presupuesto_eur: float) -> None:
    """Upsert the budget target for `project`."""
    if project not in known_projects():
        raise ValueError(f"unknown project: {project!r}")
    if presupuesto_eur <= 0:
        raise ValueError("presupuesto_eur must be positive")

    import datetime as _dt

    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        conn.execute(
            "INSERT INTO project_budget (project, presupuesto_eur, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(project) DO UPDATE SET presupuesto_eur=excluded.presupuesto_eur, updated_at=excluded.updated_at",
            (project, presupuesto_eur, now),
        )
        conn.commit()
    finally:
        conn.close()


def set_labor_rate(rate_eur_hour: float, basis: str | None = None) -> None:
    """Insert a new labor_rates row (the latest row is what the views use)."""
    if rate_eur_hour <= 0:
        raise ValueError("rate_eur_hour must be positive")

    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        conn.execute(
            "INSERT INTO labor_rates (rate_eur_hour, basis) VALUES (?, ?)",
            (rate_eur_hour, basis),
        )
        conn.commit()
    finally:
        conn.close()


def get_labor_rate() -> float:
    """Return the latest labor_rates.rate_eur_hour, mirroring the views' ORDER BY."""
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        row = conn.execute(
            "SELECT rate_eur_hour FROM labor_rates ORDER BY effective_date DESC, id DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else 0.0
    finally:
        conn.close()


def get_budget_status(project: str | None = None) -> list[dict]:
    """Query v_budget_deviation, optionally filtered to a single project."""
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        if project:
            rows = conn.execute(
                "SELECT * FROM v_budget_deviation WHERE project=?", (project,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM v_budget_deviation").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_project_roi(project: str | None = None) -> list[dict]:
    """Query v_project_roi, optionally filtered to a single project."""
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        if project:
            rows = conn.execute(
                "SELECT * FROM v_project_roi WHERE project=?", (project,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM v_project_roi").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
