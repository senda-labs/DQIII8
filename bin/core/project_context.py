#!/usr/bin/env python3
"""Project SSOT — single resolver for "which project is this action for".

Replaces the two dead file-glob resolvers in session_start.py and
user_prompt_submit.py (both targeted /root/dqiii8/projects/, which does not
exist — Correction C) and the ad-hoc cwd-sniffing duplicated across
pre_tool_use.py, openrouter_wrapper.py and pal/engine.py.

Precedence (Correction I.1 — DQIII8_PROJECT is a process-local CACHE, not a
durable precedence step; a stale/foreign env var must not shadow a real DB
declaration made from a different process, e.g. a Telegram /proyecto sent
while a long-running CC session is open):
  1. explicit `project=` arg from the caller
  2. DQIII8_PROJECT env var, but ONLY if set less than ENV_CACHE_TTL_S ago
     (stamped alongside it as DQIII8_PROJECT_SET_AT) — otherwise re-checked
     against the DB below
  3. open project_context row for this session_id
  4. open project_context row for scope='global' (the user's declaration)
  5. cwd match on /my-projects/<x>/ (preserves pre_tool_use.py's prior behavior)
  6. literal 'dqiii8-core' (matches session_start.py/post_tool_use.py's
     existing hardcoded fallback — project can never be NULL on a new row)
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

DQIII8_ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
DB_PATH = DQIII8_ROOT / "database" / "dqiii8.db"
MY_PROJECTS_DIR = DQIII8_ROOT / "my-projects"
CORE_PROJECT = "dqiii8-core"
ENV_CACHE_TTL_S = 300  # env var trusted for 5 minutes without a DB re-check

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

    Fails open on any DB error (steps 3/4): log at DEBUG, skip DB resolution,
    fall through to the cwd/default steps rather than blocking the hot INSERT
    path a caller is usually on (Stage 2 panel-pass-2 concern re: SQLITE_BUSY).
    """
    if project:
        return project

    env_project = os.environ.get("DQIII8_PROJECT", "")
    if env_project:
        set_at = os.environ.get("DQIII8_PROJECT_SET_AT", "")
        try:
            fresh = set_at and (time.time() - float(set_at)) < ENV_CACHE_TTL_S
        except ValueError:
            fresh = False
        if fresh:
            return env_project

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
        if slug:
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

    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
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

    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
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
    return _open_context_row(scope, db_timeout=10)
