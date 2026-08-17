"""Error taxonomy for metadata_audit.py / metadata_remove.py.

Distinguishes corrupt-but-benign input (degrade to report-only, never write)
from adversarial input (abort entirely, no partial processing, no backup).
Each class carries the process exit code its CLI should use when this is the
worst outcome seen across a run.
"""

from __future__ import annotations

import enum


class ErrorClass(enum.Enum):
    UNSUPPORTED = ("unsupported", 0)
    EXTENSION_MISMATCH = ("extension_mismatch", 1)
    CORRUPT = ("corrupt", 1)
    ADVERSARIAL = ("adversarial", 3)
    ENCRYPTED_OR_SIGNED = ("encrypted_or_signed", 2)
    ENGINE_FAILURE = ("engine_failure", 4)

    def __init__(self, label: str, exit_code: int) -> None:
        self.label = label
        self.exit_code = exit_code


class MetadataToolError(Exception):
    """Raised by fmt_* modules to signal a classified failure for one file."""

    def __init__(self, error_class: ErrorClass, message: str) -> None:
        super().__init__(message)
        self.error_class = error_class
        self.message = message


def rank(cls: ErrorClass) -> int:
    """Severity rank for "which outcome does the operator most need to see".

    NOT the raw exit code: ADVERSARIAL (exit 3) must outrank ENGINE_FAILURE
    (exit 4), because a batch containing both would otherwise report only the
    benign engine failure and hide that a hostile input was present at all —
    exactly the masking this taxonomy exists to prevent.
    """
    return 100 if cls is ErrorClass.ADVERSARIAL else cls.exit_code


def worst(classes: list[ErrorClass]) -> ErrorClass | None:
    """Highest-severity class among those seen (see rank()), or None."""
    if not classes:
        return None
    return max(classes, key=rank)
