#!/usr/bin/env python3
"""Manual, human-invoked removal of hidden/invisible Unicode characters from
arbitrary files or directories — NOT limited to the git staging area the way
watermark_scan.py --fix is. This exists for the cases that tool deliberately
doesn't cover: a downloaded dataset, an unpacked client deliverable, text
received from another AI tool, anything not currently staged for commit.

Never runs automatically. No CI mode, no pre-commit hook, no default write.
Dry-run is the default for every invocation: pass --apply to actually
rewrite anything. This is intentional and matches the standing constraint
on this whole feature area: watermark removal is always a decision a human
makes explicitly, never something that happens as a side effect of another
action.

Two removal tiers, both opt-in:
  (default)  only the categories watermark_scan.py itself considers safe to
             strip automatically once a human asks for it: zero-width space,
             invisible math operators, deprecated invisible format chars +
             soft hyphen, and BOM (for .py/.js/.ts). No ambiguity about
             intent — nothing here has a legitimate rendered purpose.
  --all      also strips bidi overrides, Unicode Tag block, line/paragraph
             separators, and the report-only set (ZWNJ/ZWJ/variation
             selectors outside emoji context). These CAN have legitimate
             uses (right-to-left text, real emoji sequences the context
             heuristic missed) or be active attack evidence worth
             preserving for investigation — --all is a deliberate override
             of that caution and requires --yes on top of --apply.

Every file that would be changed gets a `.bak` written next to it before
the rewrite (refuses to overwrite an existing .bak — investigate/remove it
by hand first rather than silently losing an earlier backup). Symlinks are
skipped, never followed. File mode is preserved.

Usage:
    python3 bin/tools/watermark_remove.py --dir PATH             # dry-run, safe tier
    python3 bin/tools/watermark_remove.py --dir PATH --apply     # actually strip, safe tier
    python3 bin/tools/watermark_remove.py --file PATH --apply --all --yes
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import watermark_scan as ws  # noqa: E402

MAX_DIR_FILES = 5000
ALL_TIER_CATEGORIES = {"bidi", "tag", "linesep", "report_only"}


def _target_categories(path: Path, strip_all: bool) -> set[str]:
    cats = set(ws._fixable_categories(path))
    if strip_all:
        cats |= ALL_TIER_CATEGORIES
    return cats


def collect_files(dir_path: Path | None, file_path: Path | None) -> tuple[list[Path], dict[str, int]]:
    skip_counts: dict[str, int] = {}
    if file_path is not None:
        if file_path.is_symlink():
            return [], {"symlink": 1}
        return [file_path], {}

    files: list[Path] = []
    count = 0
    for path in sorted(dir_path.rglob("*")):
        if path.is_symlink():
            skip_counts["symlink"] = skip_counts.get("symlink", 0) + 1
            continue
        if not path.is_file():
            continue
        count += 1
        if count > MAX_DIR_FILES:
            print(
                f"watermark-remove: stopped after {MAX_DIR_FILES} files (more remain under {dir_path}) — narrow --dir",
                file=sys.stderr,
            )
            break
        files.append(path)
    return files, skip_counts


def remove_from_file(path: Path, apply: bool, strip_all: bool) -> tuple[list[dict], bool]:
    """Returns (findings_in_target_tier, actually_written)."""
    try:
        raw = path.read_bytes()
    except OSError:
        return [], False

    findings = ws.scan_bytes(path, raw)
    if not findings:
        return [], False

    target_cats = _target_categories(path, strip_all)
    to_strip = {f["codepoint"] for f in findings if f["category"] in target_cats}
    if not to_strip:
        return findings, False

    if not apply:
        return findings, False

    text, reason = ws._decode(raw)
    if text is None:
        print(f"  skip (undecodable, reason={reason}): {path}", file=sys.stderr)
        return findings, False

    strip_chars = {int(cp[2:], 16) for cp in to_strip}
    new_text = "".join(ch for ch in text if ord(ch) not in strip_chars)
    if new_text == text:
        return findings, False

    bak = path.with_name(path.name + ".bak")
    if bak.exists():
        print(f"  skip (backup already exists, resolve it first): {bak}", file=sys.stderr)
        return findings, False

    try:
        mode = path.stat().st_mode
    except OSError:
        mode = None

    bak.write_bytes(raw)
    if mode is not None:
        os.chmod(bak, mode)

    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(new_text, encoding="utf-8")
    if mode is not None:
        os.chmod(tmp, mode)
    tmp.replace(path)
    print(f"  removed {len(to_strip)} codepoint(s) from {path}  (backup: {bak})")
    return findings, True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dir", type=Path, help="Recursively process this directory.")
    group.add_argument("--file", type=Path, help="Process a single file.")
    parser.add_argument("--apply", action="store_true", help="Actually rewrite files. Without it, this is a dry-run report only.")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Also strip bidi/tag/linesep/report-only categories, not just the safe tier. "
        "Requires --yes as an explicit second confirmation.",
    )
    parser.add_argument("--yes", action="store_true", help="Required alongside --apply --all — explicit confirmation for the risky tier.")
    args = parser.parse_args()

    if args.dir is not None and not args.dir.is_dir():
        print(f"watermark-remove: not a directory: {args.dir}", file=sys.stderr)
        return 2
    if args.file is not None and not args.file.is_file() and not args.file.is_symlink():
        print(f"watermark-remove: not a file: {args.file}", file=sys.stderr)
        return 2
    if args.all and args.apply and not args.yes:
        print("watermark-remove: --apply --all also needs --yes (explicit confirmation for the risky tier).", file=sys.stderr)
        return 2

    files, skip_counts = collect_files(args.dir, args.file)

    total_findings = 0
    total_target = 0
    total_written = 0
    for path in files:
        findings, written = remove_from_file(path, args.apply, args.all)
        if not findings:
            continue
        total_findings += len(findings)
        target_cats = _target_categories(path, args.all)
        total_target += len([f for f in findings if f["category"] in target_cats])
        if written:
            total_written += 1

    if skip_counts:
        parts = ", ".join(f"{k}={v}" for k, v in sorted(skip_counts.items()))
        print(f"watermark-remove: skipped {sum(skip_counts.values())} file(s): {parts}", file=sys.stderr)

    if total_findings == 0:
        print("watermark-remove: no hidden/invisible characters found.")
        return 0

    tier = "safe + risky (--all)" if args.all else "safe"
    if args.apply:
        print(
            f"watermark-remove: {total_target}/{total_findings} finding(s) in the {tier} tier "
            f"removed across {total_written} file(s). {total_findings - total_target} finding(s) "
            "outside the selected tier were left untouched — re-run with --all --yes to include them."
        )
    else:
        print(
            f"watermark-remove: DRY RUN — {total_target}/{total_findings} finding(s) in the {tier} tier "
            f"would be removed. Re-run with --apply to actually write changes."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
