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
from metadata_lib.safeio import write_new_file  # noqa: E402

MAX_DIR_FILES = 5000
# Neither --dir nor --file had any per-file size ceiling — remove_from_file()
# reads the whole file into memory (path.read_bytes()) unconditionally. A
# pathologically large single file was unbounded in both modes, unlike
# metadata_remove.py's --dir sweep which iter_files already caps by cumulative
# bytes. Matches metadata_lib.safeio.DEFAULT_MAX_BYTES for one shared ceiling
# across the toolchain.
MAX_FILE_BYTES = 2 * 1024 * 1024 * 1024

# Precedence: truncated (5) > write refused (1) > success (0). Shares
# metadata_remove.py's value so the toolchain has one exit-code taxonomy.
EXIT_TRUNCATED = 5
ALL_TIER_CATEGORIES = {"bidi", "tag", "linesep", "report_only"}


def _encode_like_input(raw: bytes, text: str) -> bytes:
    """Re-encode `text` in the same encoding ws._decode() used to read `raw`,
    preserving the original byte-order mark. Writing UTF-8 unconditionally
    silently transcoded every UTF-16 file the scanner deliberately supports.
    """
    bom = raw[:2]
    if bom == b"\xff\xfe":
        return b"\xff\xfe" + text.encode("utf-16-le")
    if bom == b"\xfe\xff":
        return b"\xfe\xff" + text.encode("utf-16-be")
    return text.encode("utf-8")


def _target_categories(path: Path, strip_all: bool) -> set[str]:
    cats = set(ws._fixable_categories(path))
    if strip_all:
        cats |= ALL_TIER_CATEGORIES
    return cats


def collect_files(
    dir_path: Path | None, file_path: Path | None
) -> tuple[list[Path], dict[str, int], str | None]:
    """Returns (files, skip_counts, truncated_reason)."""
    skip_counts: dict[str, int] = {}
    if file_path is not None:
        if file_path.is_symlink():
            return [], {"symlink": 1}, None
        return [file_path], {}, None

    files: list[Path] = []
    truncated: str | None = None
    count = 0
    for path in dir_path.rglob("*"):
        if path.is_symlink():
            skip_counts["symlink"] = skip_counts.get("symlink", 0) + 1
            continue
        if not path.is_file():
            continue
        if path.suffix in (".bak", ".tmp"):
            continue
        try:
            oversized = path.stat().st_size > MAX_FILE_BYTES
        except OSError:
            oversized = False  # let the per-file read in remove_from_file report it
        if oversized:
            skip_counts["oversized"] = skip_counts.get("oversized", 0) + 1
            continue
        count += 1
        if count > MAX_DIR_FILES:
            truncated = f"stopped after {MAX_DIR_FILES} files (more remain under {dir_path}) — narrow --dir"
            print(f"watermark-remove: {truncated}", file=sys.stderr)
            break
        files.append(path)
    return sorted(files), skip_counts, truncated


def remove_from_file(path: Path, apply: bool, strip_all: bool) -> tuple[list[dict], bool, bool]:
    """Returns (findings_in_target_tier, actually_written, refused).

    `refused` distinguishes "this tool wanted to write and could not" from the
    benign not-written cases (dry run, nothing in the selected tier, no-op edit).
    Collapsing the two is how a run in which every write was blocked could report
    "removed across 0 file(s)" and still exit 0.
    """
    try:
        raw = path.read_bytes()
    except OSError as e:
        # Previously an invisible skip: a file the tool could not even read was
        # indistinguishable from a file with nothing to remove.
        print(f"  skip (unreadable: {e}): {path}", file=sys.stderr)
        return [], False, True

    findings = ws.scan_bytes(path, raw)
    if not findings:
        return [], False, False

    target_cats = _target_categories(path, strip_all)
    to_strip = {f["codepoint"] for f in findings if f["category"] in target_cats}
    if not to_strip:
        return findings, False, False

    if not apply:
        return findings, False, False

    text, reason = ws._decode(raw)
    if text is None:
        print(f"  skip (undecodable, reason={reason}): {path}", file=sys.stderr)
        return findings, False, True

    strip_chars = {int(cp[2:], 16) for cp in to_strip}
    new_text = "".join(ch for ch in text if ord(ch) not in strip_chars)
    if new_text == text:
        return findings, False, False

    if path.is_symlink():
        print(f"  skip (symlink refused): {path}", file=sys.stderr)
        return findings, False, True

    bak = path.with_name(path.name + ".bak")
    if bak.is_symlink() or bak.exists():
        print(f"  skip (backup already exists, resolve it first): {bak}", file=sys.stderr)
        return findings, False, True

    try:
        mode = path.stat().st_mode
    except OSError:
        mode = None

    # Both side files go through safeio's single hardened primitive
    # (O_CREAT|O_EXCL|O_NOFOLLOW) — a pre-planted `.bak`/`.tmp` symlink can
    # never redirect either write to a victim path.
    try:
        write_new_file(bak, raw, mode=mode)
    except FileExistsError:
        print(f"  skip (backup already exists, resolve it first): {bak}", file=sys.stderr)
        return findings, False, True
    except OSError as e:
        print(f"  skip (cannot write backup: {e}): {bak}", file=sys.stderr)
        return findings, False, True

    tmp = path.with_name(path.name + ".tmp")
    try:
        write_new_file(tmp, _encode_like_input(raw, new_text), mode=mode)
    except (FileExistsError, OSError) as e:
        bak.unlink(missing_ok=True)
        print(f"  skip (cannot write tmp: {e}): {tmp}", file=sys.stderr)
        return findings, False, True
    os.replace(tmp, path)
    print(f"  removed {len(to_strip)} codepoint(s) from {path}  (backup: {bak})")
    return findings, True, False


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
    if args.file is not None and args.file.is_symlink():
        # A --dir sweep discloses a symlinked member via skip_counts while still
        # reporting on every other real file, so "clean" there is truthful. A
        # single --file target has nothing else to report on: letting it fall
        # through to collect_files' symlink skip made the whole run's summary
        # "no hidden/invisible characters found" — a false clean identical in kind
        # to F6, just on the --file path instead of --dir. metadata_remove.py
        # already refuses this case outright; match that discipline here.
        print(f"watermark-remove: refusing symlinked --file target: {args.file}", file=sys.stderr)
        return 2
    if args.file is not None and not args.file.is_file():
        print(f"watermark-remove: not a file: {args.file}", file=sys.stderr)
        return 2
    if args.file is not None:
        # remove_from_file() reads the whole file into memory unconditionally
        # (path.read_bytes()) with no ceiling — a pathologically large single
        # file is unbounded here, unlike metadata_remove.py's --dir sweep which
        # iter_files already caps by cumulative bytes.
        try:
            file_size = args.file.stat().st_size
        except OSError as e:
            print(f"watermark-remove: cannot stat {args.file}: {e}", file=sys.stderr)
            return 2
        if file_size > MAX_FILE_BYTES:
            print(
                f"watermark-remove: {args.file} is {file_size} bytes, exceeding the "
                f"{MAX_FILE_BYTES}-byte per-file ceiling — refusing rather than reading an "
                "unbounded file fully into memory.",
                file=sys.stderr,
            )
            return 2
    if args.all and args.apply and not args.yes:
        print("watermark-remove: --apply --all also needs --yes (explicit confirmation for the risky tier).", file=sys.stderr)
        return 2

    files, skip_counts, truncated = collect_files(args.dir, args.file)

    total_findings = 0
    total_target = 0
    total_written = 0
    total_refused = 0
    for path in files:
        findings, written, refused = remove_from_file(path, args.apply, args.all)
        if refused:
            total_refused += 1
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

    if total_findings == 0 and total_refused == 0:
        if truncated:
            print("watermark-remove: PARTIAL SCAN — nothing found in the portion scanned, but the scan was truncated.")
            return EXIT_TRUNCATED
        print("watermark-remove: no hidden/invisible characters found.")
        return 0

    tier = "safe + risky (--all)" if args.all else "safe"
    if args.apply:
        # "eligible" and "removed" are reported separately: conflating them let a
        # run in which every write was refused still read as a successful clean.
        print(
            f"watermark-remove: {total_target}/{total_findings} finding(s) in the {tier} tier "
            f"were eligible; rewrote {total_written} file(s). {total_findings - total_target} finding(s) "
            "outside the selected tier were left untouched — re-run with --all --yes to include them."
        )
        if total_refused:
            print(
                f"watermark-remove: {total_refused} file(s) could NOT be written (see skip lines above) "
                "— those findings are still present.",
                file=sys.stderr,
            )
    else:
        print(
            f"watermark-remove: DRY RUN — {total_target}/{total_findings} finding(s) in the {tier} tier "
            f"would be removed. Re-run with --apply to actually write changes."
        )

    if truncated:
        return EXIT_TRUNCATED
    if total_refused:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
