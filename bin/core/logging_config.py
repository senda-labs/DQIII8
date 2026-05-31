#!/usr/bin/env python3
"""
DQIII8 centralised logging configuration.

Usage (in any bin/ module):
    from bin.core.logging_config import get_logger
    log = get_logger(__name__)
    log.debug("pipeline: domain=%s chunks=%d", domain, n)

Log file: $DQIII8_ROOT/var/log/dqiii8.log (10 MB × 5 backups, JSON lines).
var/log/ is auto-created; falls back to NullHandler on PermissionError (Windows / read-only FS).
stderr handler at WARNING+ is always active so critical messages surface.
"""

import json
import logging
import logging.handlers
import os
import time
from pathlib import Path


class _JsonFormatter(logging.Formatter):
    """Single-line JSON log records for easy grep / jq parsing."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "module": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def _build_root_logger() -> None:
    """Configure the root logger once per process."""
    root = logging.getLogger("dqiii8")
    if root.handlers:
        return  # already configured

    root.setLevel(logging.DEBUG)

    # File handler — JSON, rotating 10 MB × 5
    _root_env = os.environ.get("DQIII8_ROOT")
    _root_dir = Path(_root_env).resolve() if _root_env else Path(__file__).resolve().parents[2]
    _log_dir = _root_dir / "var" / "log"

    try:
        _log_dir.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError):
        pass

    if _log_dir.exists():
        fh = logging.handlers.RotatingFileHandler(
            str(_log_dir / "dqiii8.log"),
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(_JsonFormatter())
        root.addHandler(fh)
    else:
        root.addHandler(logging.NullHandler())

    # stderr handler — WARNING+ so errors always surface in docker/systemd logs
    sh = logging.StreamHandler()
    sh.setLevel(logging.WARNING)
    sh.setFormatter(logging.Formatter("[%(name)s] %(levelname)s %(message)s"))
    root.addHandler(sh)


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the 'dqiii8' namespace.

    If *name* already starts with 'dqiii8', it is used verbatim.
    Otherwise 'dqiii8.' is prepended.
    """
    _build_root_logger()
    if not name.startswith("dqiii8"):
        name = f"dqiii8.{name}"
    return logging.getLogger(name)
