#!/usr/bin/env python3
"""Ad-hoc, read-only metadata/watermark audit for binary files — detection
only, structurally incapable of removing anything (this module imports no
write path anywhere; tests/test_metadata_no_write_audit.py AST-walks this
file to enforce that mechanically, not just by convention).

Covers EXIF/IPTC/XMP (images), PDF document-info/XMP/embedded objects, OOXML
document properties, and C2PA content-credentials manifests (all carriers,
including BMFF which metadata_remove.py can only detect, never strip).

Companion to watermark_audit.py (hidden Unicode text) — this tool is for the
binary-metadata side of the same standing rule: removal is always a human
decision, made explicitly with metadata_remove.py, never automatic.

Usage:
    python3 bin/tools/metadata_audit.py --dir path/to/thing
    python3 bin/tools/metadata_audit.py --file report.pdf --json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from metadata_lib import detect, fmt_c2pa  # noqa: E402
from metadata_lib.errors import MetadataToolError  # noqa: E402
from metadata_lib.report import Finding, Summary, build_report  # noqa: E402
from metadata_lib.safeio import iter_files  # noqa: E402

TOOL_VERSION = "1.0.0"

# Exit-code precedence, stated explicitly so a truncated-AND-degraded sweep is not
# undefined: truncated (5) > degraded (2) > findings (1) > clean (0). Truncation wins
# because a partial scan is strictly worse information than a degraded complete one.
# Known, accepted ambiguity: 2 is also returned for usage errors (bad --dir/--file).
EXIT_TRUNCATED = 5


def _exit_code(findings: list, degraded: list, truncated: str | None) -> int:
    if truncated:
        return EXIT_TRUNCATED
    if degraded:
        return 2
    return 1 if findings else 0


def _engine_versions() -> dict:
    engines = {}
    try:
        import pikepdf

        engines["pikepdf"] = pikepdf.__version__
    except Exception:  # noqa: BLE001
        engines["pikepdf"] = "absent"
    try:
        import subprocess

        from metadata_lib.fmt_image import resolve_exiftool

        exe = resolve_exiftool()
        if exe:
            out = subprocess.run(
                [exe, "-ver"], capture_output=True, text=True, timeout=5, stdin=subprocess.DEVNULL
            )
            engines["exiftool"] = out.stdout.strip() or "unknown"
        else:
            engines["exiftool"] = "absent"
    except Exception:  # noqa: BLE001
        engines["exiftool"] = "absent"
    try:
        import c2pa  # noqa: F401

        engines["c2pa"] = "present"
    except Exception:  # noqa: BLE001
        engines["c2pa"] = "absent"
    return engines


def inspect_file(path: Path) -> tuple[list[Finding], str | None]:
    """Returns (findings, skip_reason). Read-only, never writes."""
    try:
        raw = path.read_bytes()
    except OSError:
        return [], "unreadable"
    if not raw:
        return [], "corrupt"

    try:
        det = detect.detect(path, raw)
    except MetadataToolError as e:
        # Detection itself can reject a hostile package (zip guards). Surface
        # it as an adversarial finding — never as an exit-0 "unsupported".
        return (
            [
                Finding(
                    path=str(path),
                    format="ooxml",
                    location="<package>",
                    field="adversarial_input",
                    tier="safe",
                    severity="high",
                    removable=False,
                    note=e.message,
                    error_class=e.error_class,
                )
            ],
            None,
        )
    if det.mismatch:
        return (
            [
                Finding(
                    path=str(path),
                    format=det.format,
                    location="<extension>",
                    field="extension_mismatch",
                    tier="safe",
                    severity="high",
                    removable=False,
                    note=det.mismatch,
                )
            ],
            "extension_mismatch",
        )

    findings: list[Finding] = []

    if det.format == "jpeg":
        findings += fmt_c2pa.detect_jpeg_c2pa(str(path), raw)
        findings += _inspect_image_exif(path, raw, "jpeg")
    elif det.format == "png":
        findings += fmt_c2pa.detect_png_c2pa(str(path), raw)
        findings += _inspect_image_exif(path, raw, "png")
    elif det.format == "webp":
        findings += fmt_c2pa.detect_webp_c2pa(str(path), raw)
        findings += _inspect_image_exif(path, raw, "webp")
    elif det.format == "tiff":
        findings += _inspect_image_exif(path, raw, "tiff")
    elif det.format == "bmff":
        findings += fmt_c2pa.detect_bmff_c2pa(str(path), raw)
    elif det.format == "pdf":
        findings += _inspect_pdf(path, raw)
    elif det.format == "ooxml":
        if det.subtype == "xlsb":
            return (
                [
                    Finding(
                        path=str(path),
                        format="ooxml",
                        location="<package>",
                        field="unsupported_subtype",
                        tier="safe",
                        severity="info",
                        removable=False,
                        note="xlsb carries binary parts — out of scope for detection/removal",
                    )
                ],
                None,
            )
        if det.subtype is None:
            return [], "unsupported_format"
        from metadata_lib import fmt_ooxml

        findings += fmt_ooxml.inspect(path, raw, det.subtype)
    else:
        return [], "unsupported_format"

    return findings, None


def _inspect_image_exif(path: Path, raw: bytes, fmt: str) -> list[Finding]:
    from metadata_lib import fmt_image

    try:
        return fmt_image.inspect(path, raw, fmt)
    except Exception:  # noqa: BLE001
        return []


def _inspect_pdf(path: Path, raw: bytes) -> list[Finding]:
    from metadata_lib import fmt_pdf

    try:
        return fmt_pdf.inspect(path, raw)
    except Exception:  # noqa: BLE001
        return []


def scan_directory(root: Path, max_files: int, max_bytes: int):
    """Returns (findings, skip_counts, files_scanned, truncated_reason).

    truncated_reason is non-None when a cap stopped the walk early. It must reach
    the report: a partial sweep printed as "no findings" is the worst failure mode
    available to a privacy-assurance tool.
    """
    findings: list[Finding] = []
    skip_counts: dict[str, int] = {}
    files_scanned = 0
    truncated: str | None = None
    for path, skip in iter_files(root, max_files=max_files, max_bytes=max_bytes):
        if skip is not None:
            if path is None:
                truncated = skip
                print(f"metadata-audit: {skip}", file=sys.stderr)
                continue
            skip_counts[skip] = skip_counts.get(skip, 0) + 1
            continue
        fs, reason = inspect_file(path)
        files_scanned += 1
        if reason:
            skip_counts[reason] = skip_counts.get(reason, 0) + 1
        findings.extend(fs)
    return findings, skip_counts, files_scanned, truncated


def report(
    findings: list[Finding],
    skip_counts: dict,
    files_scanned: int,
    root: str,
    as_json: bool,
    truncated: str | None = None,
) -> int:
    import datetime

    engines = _engine_versions()
    degraded = []
    if engines.get("exiftool") == "absent":
        degraded.append("exiftool absent — image metadata detection is pure-Python fallback (limited)")

    summary = Summary(files_scanned=files_scanned, files_with_findings=len({f.path for f in findings}))
    for f in findings:
        summary.by_tier[f.tier] = summary.by_tier.get(f.tier, 0) + 1
    # Merge, never filter: the preset keys are defaults, not an allowlist. Dropping
    # an unrecognised reason (e.g. "unreadable") made files that were never actually
    # examined vanish from the JSON report — indistinguishable from a clean scan.
    for k, v in skip_counts.items():
        summary.skipped[k] = summary.skipped.get(k, 0) + v

    if as_json:
        import json

        data = build_report(
            "metadata_audit",
            TOOL_VERSION,
            datetime.datetime.now(datetime.timezone.utc).isoformat(),
            root,
            summary,
            engines,
            degraded,
            findings,
            truncated,
        )
        print(json.dumps(data, indent=2))
        return _exit_code(findings, degraded, truncated)

    if skip_counts:
        parts = ", ".join(f"{k}={v}" for k, v in sorted(skip_counts.items()))
        print(f"metadata-audit: skipped/flagged {sum(skip_counts.values())} file(s): {parts}", file=sys.stderr)
    if degraded:
        for d in degraded:
            print(f"metadata-audit: DEGRADED — {d}", file=sys.stderr)

    if not findings:
        if truncated:
            print("metadata-audit: PARTIAL SCAN — no findings in the portion scanned, but the scan was truncated.")
        else:
            print("metadata-audit: no metadata/watermark findings.")
        return _exit_code(findings, degraded, truncated)

    by_file: dict[str, list[Finding]] = {}
    for f in findings:
        by_file.setdefault(f.path, []).append(f)

    print(f"metadata-audit: {len(findings)} finding(s) in {len(by_file)} file(s)")
    for file_str, fs in by_file.items():
        print(f"\n{file_str}")
        for f in fs:
            print(f"  [{f.tier}] {f.format} {f.location} — {f.field}{' — ' + f.note if f.note else ''}")

    print(
        "\nDetection only — nothing was modified. Removal is a manual decision: "
        "re-run with metadata_remove.py --dir/--file (dry-run by default; "
        "--apply to write, --all --yes for the riskier tier)."
    )
    return _exit_code(findings, degraded, truncated)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dir", type=Path, help="Recursively scan this directory (read-only).")
    group.add_argument("--file", type=Path, help="Scan a single file (read-only).")
    parser.add_argument("--json", action="store_true", help="Emit the versioned machine-readable report.")
    parser.add_argument("--max-files", type=int, default=5000)
    parser.add_argument("--max-bytes", type=int, default=2 * 1024 * 1024 * 1024)
    args = parser.parse_args()

    if args.dir is not None:
        if not args.dir.is_dir():
            print(f"metadata-audit: not a directory: {args.dir}", file=sys.stderr)
            return 2
        findings, skip_counts, files_scanned, truncated = scan_directory(
            args.dir, args.max_files, args.max_bytes
        )
        root = str(args.dir)
    else:
        if args.file.is_symlink() or not args.file.is_file():
            print(f"metadata-audit: not a file (or is a symlink): {args.file}", file=sys.stderr)
            return 2
        findings, reason = inspect_file(args.file)
        skip_counts = {reason: 1} if reason else {}
        files_scanned = 1
        truncated = None
        root = str(args.file)

    return report(findings, skip_counts, files_scanned, root, args.json, truncated)


if __name__ == "__main__":
    sys.exit(main())
