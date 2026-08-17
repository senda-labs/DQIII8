#!/usr/bin/env python3
"""Ad-hoc, read-only Unicode watermark/hidden-character audit — detection only,
NEVER removes anything. This is the deliberate port of the one genuinely useful
idea in github.com/guillaumemeyer/watermarks-remover — its context-aware
classification approach — reimplemented on top of our own scanner
(bin/tools/watermark_scan.py). It does NOT port that repo's removal layers
(Unicode strip, LLM-rewrite statistical-watermark removal, C2PA/EXIF/XMP
metadata stripping): removing a watermark is a human decision made file-by-file
with git checked out (see watermark_scan.py --fix, which is deliberately
narrow, manual, and git-staged-only), never a bulk or automated operation —
and this tool has no --fix flag at all, on purpose.

Two modes, both read-only:
  --dir PATH     recursively scan any directory, not just git-staged files —
                  e.g. an unpacked client deliverable, a downloaded dataset,
                  code received from a third party.
  --text PATH|-  scan a text file, or '-' for stdin — e.g. paste content
                  received from another AI tool (ChatGPT, DeepSeek, ...)
                  before trusting or reusing it.

Usage:
    python3 bin/tools/watermark_audit.py --dir path/to/thing
    pbpaste | python3 bin/tools/watermark_audit.py --text -
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import watermark_scan as ws  # noqa: E402

MAX_DIR_FILES = 5000  # sanity cap so a huge --dir reports partial results loudly, not hangs silently

# Exit-code precedence for a directory sweep: truncated (5) > findings (1) > clean (0).
# Truncation outranks everything because a partial scan is strictly worse information
# than any complete result. Shares metadata_remove.py's value so there is one taxonomy.
EXIT_TRUNCATED = 5


def scan_directory(root: Path) -> tuple[list[dict], dict[str, int], str | None]:
    """Returns (findings, skip_counts, truncated_reason).

    truncated_reason is non-None when the cap stopped the walk early — the caller
    must not report a partial sweep as a clean bill.
    """
    findings: list[dict] = []
    skip_counts: dict[str, int] = {}
    truncated: str | None = None
    count = 0
    candidates: list[Path] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            skip_counts["symlink"] = skip_counts.get("symlink", 0) + 1
            continue
        if not path.is_file():
            continue
        if path.suffix in (".bak", ".tmp"):
            continue
        count += 1
        if count > MAX_DIR_FILES:
            truncated = f"stopped after {MAX_DIR_FILES} files (more remain under {root}) — narrow --dir"
            print(f"watermark-audit: {truncated}", file=sys.stderr)
            break
        candidates.append(path)

    for path in sorted(candidates):
        try:
            raw = path.read_bytes()
        except OSError:
            skip_counts["unreadable"] = skip_counts.get("unreadable", 0) + 1
            continue
        text, reason = ws._decode(raw)
        if text is None:
            skip_counts[reason] = skip_counts.get(reason, 0) + 1
            continue
        findings.extend(ws.scan_bytes(path, raw))
    return findings, skip_counts, truncated


def scan_text(text: str) -> list[dict]:
    return ws.scan_bytes(Path("<input>"), text.encode("utf-8"))


def report(findings: list[dict], skip_counts: dict[str, int], truncated: str | None = None) -> int:
    if skip_counts:
        parts = ", ".join(f"{k}={v}" for k, v in sorted(skip_counts.items()))
        print(f"watermark-audit: skipped {sum(skip_counts.values())} file(s): {parts}", file=sys.stderr)

    if not findings:
        if truncated:
            # A partial sweep must never print a clean bill: exit TRUNCATED so a
            # caller cannot read "nothing found" as "nothing is there".
            print("watermark-audit: PARTIAL SCAN — no findings in the portion scanned, but the scan was truncated.")
            return EXIT_TRUNCATED
        print("watermark-audit: no hidden/invisible characters found.")
        return 0

    by_file: dict[str, list[dict]] = {}
    for f in findings:
        by_file.setdefault(f["file"], []).append(f)

    print(f"watermark-audit: {len(findings)} finding(s) in {len(by_file)} location(s)")
    for file_str, fs in by_file.items():
        print(f"\n{file_str}")
        for f in fs:
            marker = " [SUSPICIOUS]" if f["category"] in ("bidi", "tag", "linesep") else ""
            print(
                f"  {f['line']}:{f['col']}  {f['codepoint']} ({f['label']})"
                f"  ctx={f['context']!r}{marker}"
            )
    print(
        "\nDetection only — nothing was modified. If something here needs removing, "
        "that is a decision you make by hand: for a git-staged file, "
        "`watermark_scan.py --fix` covers zero-width-space/invisible-math/"
        "invisible-ctrl/BOM only; anything else (bidi, tag, line-separator, "
        "ZWNJ/ZWJ/variation-selector-out-of-emoji-context) needs manual review — "
        "this tool will never strip it for you."
    )
    return EXIT_TRUNCATED if truncated else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dir", type=Path, help="Recursively scan this directory (read-only, follows no symlinks).")
    group.add_argument("--text", help="Scan this text file, or '-' to read from stdin.")
    args = parser.parse_args()

    if args.dir:
        if not args.dir.is_dir():
            print(f"watermark-audit: not a directory: {args.dir}", file=sys.stderr)
            return 2
        findings, skip_counts, truncated = scan_directory(args.dir)
    else:
        if args.text == "-":
            raw_text = sys.stdin.read()
        else:
            try:
                raw_text = Path(args.text).read_text(encoding="utf-8")
            except OSError as e:
                print(f"watermark-audit: cannot read {args.text}: {e}", file=sys.stderr)
                return 2
        findings, skip_counts, truncated = scan_text(raw_text), {}, None

    return report(findings, skip_counts, truncated)


if __name__ == "__main__":
    sys.exit(main())
