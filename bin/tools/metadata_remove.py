#!/usr/bin/env python3
"""Manual, human-invoked removal of embedded metadata/watermarks from binary
files — EXIF/IPTC/XMP (images), PDF document-info/XMP/embedded C2PA
manifests, and (docx only, this pass — xlsx/pptx are detection-only, see
metadata_audit.py) OOXML document properties.

Never runs automatically. No CI mode, no pre-commit hook, no default write.
Dry-run is the default for every invocation: pass --apply to actually
rewrite anything. Mirrors watermark_remove.py's grammar and the same
standing constraint: this is always a decision a human makes explicitly.

Two tiers, both opt-in:
  (default)  provenance fields with no rendered-content ambiguity — see
             metadata_lib's module docstrings for the full per-format list.
  --all      content-adjacent / harder-to-verify fields (ICC profiles, PNG
             text chunks, PDF form values/JavaScript/OutputIntents/trailer
             ID, signed documents). Requires --yes on top of --apply.

Every file that would be changed gets a `.bak` written next to it before
the rewrite (refuses to overwrite an existing .bak). Symlinks are skipped,
never followed. Write order is transform -> tmp -> validate -> backup ->
atomic replace (metadata_lib/safeio.py); a validation failure leaves the
original file completely untouched.

Usage:
    python3 bin/tools/metadata_remove.py --dir PATH                    # dry-run, safe tier
    python3 bin/tools/metadata_remove.py --dir PATH --apply            # actually strip, safe tier
    python3 bin/tools/metadata_remove.py --file PATH --apply --all --yes
"""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from metadata_lib import audit_log, detect, safeio, validate  # noqa: E402
from metadata_lib.errors import ErrorClass, MetadataToolError  # noqa: E402
from metadata_lib.safeio import iter_files  # noqa: E402
from metadata_audit import _engine_versions, inspect_file  # noqa: E402

TOOL_VERSION = "1.1.0"
# Distinct, non-zero: a sweep that hit the file/byte cap saw only part of the
# tree, and must never be indistinguishable from a complete clean run.
EXIT_TRUNCATED = 5

REMOVABLE_FORMATS = {"jpeg", "png", "webp", "pdf"}
DETECTION_ONLY_NOTE = {
    "tiff": "TIFF removal not implemented — pure structural detection only this pass",
    "bmff": "BMFF C2PA removal requires offset-preserving substitution — not implemented",
    "xlsx": "xlsx removal deferred — detection only this pass",
    "pptx": "pptx removal deferred — detection only this pass",
    "xlsb": "xlsb carries binary parts — out of scope",
}


def _transform(path: Path, raw: bytes, det, *, all_tier: bool) -> bytes:
    from metadata_lib import fmt_c2pa, fmt_image, fmt_pdf

    if det.format in ("jpeg", "png", "webp"):
        stage1 = raw
        if det.format == "jpeg":
            stage1 = fmt_c2pa.remove_jpeg_c2pa(stage1)
        elif det.format == "png":
            stage1 = fmt_c2pa.remove_png_c2pa(stage1)
        elif det.format == "webp":
            stage1 = fmt_c2pa.remove_webp_c2pa(stage1)
        return fmt_image.remove(stage1, det.format, all_tier=all_tier)

    if det.format == "pdf":
        return fmt_pdf.remove(raw, all_tier=all_tier)

    if det.format == "ooxml" and det.subtype == "docx":
        from metadata_lib import fmt_ooxml

        return fmt_ooxml.remove(raw, all_tier=all_tier)

    raise MetadataToolError(
        ErrorClass.UNSUPPORTED,
        DETECTION_ONLY_NOTE.get(det.format if det.format != "ooxml" else det.subtype, "unsupported format"),
    )


def _validate(det, original_bytes: bytes, new_bytes: bytes) -> None:
    if det.format in ("jpeg", "png", "webp"):
        validate.validate_image_structural(original_bytes, new_bytes)
    elif det.format == "pdf":
        validate.validate_pdf(original_bytes, new_bytes, allow_recovered=True)
    elif det.format == "ooxml":
        validate.validate_ooxml_structural(new_bytes, original_bytes)
        validate.validate_ooxml_reparse(new_bytes, det.subtype)


def process_file(path: Path, *, apply: bool, all_tier: bool, invocation_id: str) -> dict:
    """Returns a stats dict: {status, removed_count, error_class}."""
    try:
        raw = path.read_bytes()
    except OSError as e:
        return {"status": "unreadable", "error": str(e)}
    if not raw:
        return {"status": "corrupt"}

    try:
        det = detect.detect(path, raw)
    except MetadataToolError as e:
        return {"status": e.error_class.label, "note": e.message}
    if det.mismatch:
        return {"status": "extension_mismatch", "note": det.mismatch}

    findings, skip_reason = inspect_file(path)
    if skip_reason:
        return {"status": skip_reason}
    adversarial = next((f for f in findings if f.field == "adversarial_input"), None)
    if adversarial is not None:
        # A hostile-input abort must never be reachable as "nothing to
        # remove" (removable=False would otherwise fall through the normal
        # tier filter below and silently report success) — no .bak, no
        # transform is ever attempted.
        return {"status": ErrorClass.ADVERSARIAL.label, "note": adversarial.note}
    engine_error = next((f for f in findings if f.field == "engine_error"), None)
    if engine_error is not None:
        # Same reasoning: an encrypted/corrupt PDF or a failed exiftool run
        # produces a non-removable finding that would otherwise fall through
        # the tier filter to "no_target_tier_findings" — a status every
        # exit-code path treats as success. The class is read from the
        # finding's structured field, never re-parsed out of its note text.
        cls = engine_error.error_class or ErrorClass.ENGINE_FAILURE
        return {"status": cls.label, "note": engine_error.note}
    if not findings:
        return {"status": "clean"}

    target_findings = [f for f in findings if f.removable and (all_tier or f.tier == "safe")]
    if not target_findings:
        return {"status": "no_target_tier_findings", "total_findings": len(findings)}

    if not apply:
        return {"status": "dry_run", "target_findings": len(target_findings), "total_findings": len(findings)}

    if safeio.refuses_symlink(path):
        return {"status": "symlink_refused"}

    try:
        new_bytes = _transform(path, raw, det, all_tier=all_tier)
    except MetadataToolError as e:
        return {"status": e.error_class.label, "note": e.message}
    except Exception as e:  # noqa: BLE001
        return {"status": ErrorClass.ENGINE_FAILURE.label, "note": str(e)}

    if new_bytes == raw:
        return {"status": "no_change"}

    try:
        _validate(det, raw, new_bytes)
    except MetadataToolError as e:
        return {"status": e.error_class.label, "note": e.message}
    except Exception as e:  # noqa: BLE001
        return {"status": ErrorClass.ENGINE_FAILURE.label, "note": str(e)}

    result = safeio.atomic_replace(path, new_bytes, backup_from=raw)
    if not result.written:
        return {"status": "write_refused", "note": result.reason}

    audit_log.append(
        {
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "tool": "metadata_remove",
            "tool_version": TOOL_VERSION,
            "invocation_id": invocation_id,
            # Absolute: the log is consumed later by metadata_purge_backups from an
            # arbitrary cwd, and a relative string recorded here was unresolvable
            # there (it silently matched nothing, so backups were never reclaimed).
            "path": str(path.resolve()),
            "format": det.format,
            "tier": "all" if all_tier else "safe",
            "mode": "apply",
            "sha256_before": validate.sha256(raw),
            "sha256_after": validate.sha256(new_bytes),
            "backup": str(result.backup_path),
            "removed": [{"location": f.location, "field": f.field, "count": 1} for f in target_findings],
            "left_in_place": [
                {"location": f.location, "field": f.field, "count": 1, "reason": "tier"}
                for f in findings
                if f not in target_findings
            ],
            "outcome": "written",
        }
    )
    return {"status": "written", "removed_count": len(target_findings)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dir", type=Path, help="Recursively process this directory.")
    group.add_argument("--file", type=Path, help="Process a single file.")
    parser.add_argument("--apply", action="store_true", help="Actually rewrite files. Without it, dry-run only.")
    parser.add_argument("--all", action="store_true", help="Also remove the --all tier. Requires --yes.")
    parser.add_argument("--yes", action="store_true", help="Required alongside --apply --all.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--max-files", type=int, default=5000)
    parser.add_argument("--max-bytes", type=int, default=2 * 1024 * 1024 * 1024)
    args = parser.parse_args()

    if args.dir is not None and not args.dir.is_dir():
        print(f"metadata-remove: not a directory: {args.dir}", file=sys.stderr)
        return 2
    if args.file is not None and (args.file.is_symlink() or not args.file.is_file()):
        print(f"metadata-remove: not a file (or is a symlink): {args.file}", file=sys.stderr)
        return 2
    if args.all and args.apply and not args.yes:
        print("metadata-remove: --apply --all also needs --yes (explicit confirmation).", file=sys.stderr)
        return 2

    invocation_id = audit_log.new_invocation_id()

    truncated: str | None = None
    if args.file is not None:
        targets = [args.file]
        skip_counts: dict[str, int] = {}
    else:
        targets = []
        skip_counts = {}
        for path, skip in iter_files(args.dir, max_files=args.max_files, max_bytes=args.max_bytes):
            if skip is not None:
                if path is None:
                    truncated = skip
                    print(f"metadata-remove: {skip}", file=sys.stderr)
                    continue
                skip_counts[skip] = skip_counts.get(skip, 0) + 1
                continue
            targets.append(path)

    results = []
    for path in targets:
        r = process_file(path, apply=args.apply, all_tier=args.all, invocation_id=invocation_id)
        r["path"] = str(path)
        results.append(r)

    # Which engine did the stripping is a real capability difference (the
    # pure-Python fallback covers strictly less than exiftool), and until now the
    # operator had no way to tell which one had run.
    engines = _engine_versions()
    degraded = []
    if engines.get("exiftool") == "absent":
        degraded.append("exiftool absent — image metadata REMOVAL used the pure-Python fallback (narrower coverage)")

    if args.json:
        import json

        from metadata_lib.report import SCHEMA_VERSION

        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "tool": "metadata_remove",
                    "tool_version": TOOL_VERSION,
                    "invocation_id": invocation_id,
                    "results": results,
                    "skipped": skip_counts,
                    "truncated": truncated,
                    "engines": engines,
                    "degraded": degraded,
                },
                indent=2,
            )
        )
    else:
        written = [r for r in results if r["status"] == "written"]
        dry = [r for r in results if r["status"] == "dry_run"]
        errors = [r for r in results if r["status"] not in SUCCESS_STATUSES]

        if skip_counts:
            parts = ", ".join(f"{k}={v}" for k, v in sorted(skip_counts.items()))
            print(f"metadata-remove: skipped {sum(skip_counts.values())} file(s): {parts}", file=sys.stderr)

        for d in degraded:
            print(f"metadata-remove: DEGRADED — {d}", file=sys.stderr)

        for r in errors:
            print(f"  {r['status']}: {r['path']}{' — ' + r.get('note', '') if r.get('note') else ''}", file=sys.stderr)

        if args.apply:
            print(f"metadata-remove: wrote {len(written)} file(s). {len(errors)} skipped/errored.")
            # no_target_tier_findings is a "success" status, so a file whose findings
            # this tool cannot remove would otherwise vanish from the summary entirely
            # — quieter, not more honest, than the error line it replaced.
            unremovable = [r for r in results if r["status"] == "no_target_tier_findings" and r.get("total_findings")]
            if unremovable:
                total = sum(r.get("total_findings", 0) for r in unremovable)
                print(
                    f"metadata-remove: {len(unremovable)} file(s) still carry {total} finding(s) left in place — "
                    "either outside the selected tier (re-run with --all --yes) or not removable by this tool. "
                    "Run metadata_audit.py for the per-file detail.",
                    file=sys.stderr,
                )
        else:
            total = sum(r.get("target_findings", 0) for r in dry)
            print(
                f"metadata-remove: DRY RUN — {len(dry)} file(s) have {total} finding(s) in the "
                f"{'safe + risky (--all)' if args.all else 'safe'} tier. Re-run with --apply to write."
            )

    return _exit_code_for(results, truncated=truncated is not None)


SUCCESS_STATUSES = ("written", "dry_run", "clean", "no_target_tier_findings")


def _exit_code_for(results: list[dict], *, truncated: bool = False) -> int:
    """One unified worst-outcome pass over every non-success result.

    The previous two-path version resolved only statuses that happen to match
    an ErrorClass label and fell back to exit 1 for the rest — but only when
    NO labelled class was present at all. A single benign UNSUPPORTED (exit 0
    by design) in the batch was therefore enough to make the function return
    early and mask real `unreadable`/`write_refused`/`symlink_refused` errors.
    """
    label_to_class = {c.label: c for c in ErrorClass}
    codes: list[int] = []
    saw_adversarial = False
    for r in results:
        status = r["status"]
        if status in SUCCESS_STATUSES:
            continue
        cls = label_to_class.get(status)
        if cls is ErrorClass.ADVERSARIAL:
            saw_adversarial = True
        # Statuses with no ErrorClass label (unreadable, symlink_refused,
        # write_refused, no_change) are still real non-success outcomes: exit 1.
        codes.append(cls.exit_code if cls is not None else 1)
    if truncated:
        codes.append(EXIT_TRUNCATED)
    # A hostile-input signal must never be outranked by a benign engine
    # failure that merely happens to carry a higher raw exit code.
    if saw_adversarial:
        return ErrorClass.ADVERSARIAL.exit_code
    return max(codes) if codes else 0


if __name__ == "__main__":
    sys.exit(main())
