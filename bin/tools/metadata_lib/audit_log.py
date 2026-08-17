"""Versioned JSONL audit trail — var/metadata_removal.jsonl.

Records tag/part NAMES, COUNTS, and HASHES only — never the actual removed
VALUES (a GPS coordinate, a person's name). The log itself must never become
a higher-value leak target than the files it describes. A failed log append
is a stderr warning only; it never blocks or reverses a clean, and is never
conflated with a validation failure.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

LOG_SCHEMA_VERSION = 1
LOG_PATH = Path(__file__).resolve().parents[3] / "var" / "metadata_removal.jsonl"


def new_invocation_id() -> str:
    return uuid.uuid4().hex[:16]


def append(record: dict, *, log_path: Path = LOG_PATH) -> None:
    record = {"schema_version": LOG_SCHEMA_VERSION, **record}
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # O_NOFOLLOW so a symlink planted at the log path is refused (ELOOP ->
        # OSError -> the warning below) rather than followed into a victim file.
        # It only rejects a symlinked final component, so a symlinked var/ still
        # works. fchmod acts on the fd we already hold, closing the gap where a
        # path-based chmod would follow a symlink swapped in after the open.
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(log_path, flags, 0o600)
        with os.fdopen(fd, "a") as fh:
            os.fchmod(fh.fileno(), 0o600)
            fh.write(json.dumps(record, sort_keys=True) + "\n")
    except OSError as e:
        print(f"metadata-audit-log: WARNING failed to write audit log: {e}", file=sys.stderr)
