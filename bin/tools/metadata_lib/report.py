"""Finding dataclass + versioned JSON report schema shared by metadata_audit.py
and metadata_remove.py. schema_version changes are additive-only; any removal
or semantic change of an existing field bumps the version.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

from .errors import ErrorClass

SCHEMA_VERSION = 2

C2PA_SOFT_BINDING_NOTE = (
    "embedded manifest removed — this does NOT remove C2PA soft binding "
    "(a durable pixel-domain fingerprint checked against a cloud resolver, "
    "C2PA spec §2.3.13/§2.4.1-2.4.2/§18.10.5); a manifest-free file can "
    "still be matched back to its manifest by a resolver."
)


@dataclass
class Finding:
    path: str
    format: str
    location: str
    field: str
    tier: str  # "safe" | "all"
    severity: str  # "info" | "notice" | "high"
    removable: bool
    note: str = ""
    # Structured classification for field == "engine_error"/"adversarial_input"
    # findings. Carried as the enum itself so callers never have to re-parse it
    # back out of the human-facing `note` string (a label rename or a message
    # containing a colon would silently resolve to the wrong class, and this
    # value drives the process exit code).
    error_class: ErrorClass | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["error_class"] = self.error_class.label if self.error_class is not None else None
        return d


@dataclass
class Summary:
    files_scanned: int = 0
    files_with_findings: int = 0
    by_tier: dict = field(default_factory=lambda: {"safe": 0, "all": 0})
    skipped: dict = field(
        default_factory=lambda: {
            "symlink": 0,
            "unsupported_format": 0,
            "extension_mismatch": 0,
            "too_large": 0,
            "corrupt": 0,
            "encrypted": 0,
        }
    )


def build_report(
    tool: str,
    tool_version: str,
    generated_at: str,
    root: str,
    summary: Summary,
    engines: dict,
    degraded: list[str],
    findings: list[Finding],
    truncated: str | None = None,
) -> dict:
    # "truncated" is additive (null when the sweep was complete), so no
    # SCHEMA_VERSION bump: every pre-existing key keeps its meaning and presence.
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": tool,
        "tool_version": tool_version,
        "generated_at": generated_at,
        "root": root,
        "summary": asdict(summary),
        "engines": engines,
        "degraded": degraded,
        "truncated": truncated,
        "findings": [f.to_dict() for f in findings],
    }
