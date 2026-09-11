"""human_hours session tracking — shared by dqiii8_bot.py (Telegram) and dashboard.py (web).

Extracted from dqiii8_bot.py so the FastAPI dashboard process can write to
human_hours without importing the Telegram bot module (which pulls in
python-telegram-bot and its Application setup as a side-effecting import).
"""

import datetime as _dt
import re
import sqlite3

from bin.core.db import get_db

# Project names are slugs (matches my-projects/ directory naming: letters, digits,
# dot, dash, underscore). Rejecting anything else here — the one place both callers
# (dashboard.py's HTTP endpoint and dqiii8_bot.py's /hora command) go through — stops
# malformed/oversized input from ever reaching the table, instead of relying on each
# caller to re-validate (the dashboard endpoint's 200-char cap didn't cover this path;
# a 2026-09-04 stress-testing pass still got 4 garbage rows, including a ~5000-char
# string, into production human_hours before this existed).
_VALID_PROJECT_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _validate_project(project: str) -> str | None:
    """Returns an error message if `project` is not a valid slug, else None."""
    if not _VALID_PROJECT_RE.match(project):
        return (
            "Nombre de proyecto invalido (solo letras, numeros, '.', '-', '_', "
            "maximo 64 caracteres)."
        )
    return None


def hora_inicio(project: str, source: str = "manual") -> tuple[bool, str]:
    """Open a human_hours session for `project`. Returns (ok, user-facing message)."""
    err = _validate_project(project)
    if err:
        return False, err
    try:
        with get_db(timeout=30) as conn:
            conn.execute(
                "INSERT INTO human_hours (project, started_at, source) VALUES (?, ?, ?)",
                (project, _dt.datetime.now(_dt.timezone.utc).isoformat(), source),
            )
        return True, f"Sesion iniciada para '{project}'."
    except sqlite3.IntegrityError:
        return False, f"Ya hay una sesion abierta para '{project}'. Usa /hora fin primero."
    except Exception:
        return False, "Error al iniciar la sesion. Revisa los logs."


def hora_fin(project: str) -> tuple[bool, str]:
    """Close the open human_hours session for `project`, if any. Returns (ok, message)."""
    err = _validate_project(project)
    if err:
        return False, err
    try:
        with get_db(timeout=30) as conn:
            cur = conn.execute(
                "UPDATE human_hours SET ended_at = ? WHERE project = ? AND ended_at IS NULL",
                (_dt.datetime.now(_dt.timezone.utc).isoformat(), project),
            )
            rowcount = cur.rowcount
        if rowcount == 0:
            return False, f"No hay ninguna sesion abierta para '{project}'."
        return True, f"Sesion cerrada para '{project}'."
    except Exception:
        return False, "Error al cerrar la sesion. Revisa los logs."
