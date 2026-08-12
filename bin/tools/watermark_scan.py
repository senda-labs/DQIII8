#!/usr/bin/env python3
"""Scan staged files for invisible/hidden Unicode characters (watermark-style artifacts).

Scope is deliberately narrow: only files staged for commit
(`git diff --cached --diff-filter=d --name-only -z`). Never walks directories, never
touches untracked or gitignored paths — this by construction excludes client data
under my-projects/ and any large research datasets. Detection reads each file's
STAGED git index blob (`git cat-file -p :<path>`), not the working-tree copy —
the two can diverge (stage malicious content, then revert the working tree without
re-staging) and only the index content is what actually gets committed. Staged
symlinks are skipped: a symlink's blob content is the target path string, not the
target file's content, so following it would scan the wrong thing entirely.

Default mode is report-only and blocking (exit 1 if anything found). --fix is a
manual, opt-in, human-run flag — never wired into an automated hook.

Usage:
    python3 bin/tools/watermark_scan.py [--fix]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

MAX_FILE_SIZE = 1 * 1024 * 1024  # 1MB

# Bidi/directional overrides — Trojan Source (CVE-2021-42574) signature.
# Always hard-block, never auto-fixable: silent repair would destroy the
# only evidence of an active attack.
BIDI_BLOCK = {
    0x202A: "LRE",
    0x202B: "RLE",
    0x202C: "PDF",
    0x202D: "LRO",
    0x202E: "RLO",
    0x2066: "LRI",
    0x2067: "RLI",
    0x2068: "FSI",
    0x2069: "PDI",
    0x061C: "ALM",
}

# Zero-width space: only real category safe to auto-fix, and only manually.
ZWSP_FIXABLE = {0x200B: "ZWSP"}

# Legitimate in Persian/Hindi text (ZWNJ/ZWJ) and emoji presentation/ZWJ
# sequences (VS16, ideographic variation selectors). No reliable way to tell
# "watermark" from "correct use" — report only, never touched by --fix.
REPORT_ONLY_NEVER_FIX = {0x200C: "ZWNJ", 0x200D: "ZWJ"}
REPORT_ONLY_NEVER_FIX_RANGES = [
    (0xFE00, 0xFE0F, "VS1-16"),
    (0xE0100, 0xE01EF, "VS17-256"),
]

BOM = 0xFEFF
BOM_FIXABLE_EXTENSIONS = {".py", ".js", ".ts"}


def staged_files() -> list[Path]:
    # -z: NUL-separated, unquoted paths. Without it, git C-quotes any non-ASCII
    # filename (e.g. "café.py" -> "\"caf\\303\\251.py\""); that quoted literal
    # then fails Path.exists() downstream and the file is silently skipped —
    # a real bypass for any staged file with a non-ASCII name.
    out = subprocess.run(
        ["git", "diff", "--cached", "--diff-filter=d", "--name-only", "-z"],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        print(f"watermark-scan: not a git repository: {out.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return [Path(p) for p in out.stdout.split("\0") if p]


def staged_is_symlink(path: Path) -> bool:
    """True if the staged (index) entry for this path is a symlink (mode 120000)."""
    out = subprocess.run(
        ["git", "ls-files", "-s", "--", path.as_posix()],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.startswith("120000 ")


def staged_blob_bytes(path: Path) -> bytes | None:
    """Read the file's content as it will actually be committed (the git index
    blob), not the working-tree file. These can diverge: a file can be staged
    with malicious content, then the working-tree copy reverted to something
    clean WITHOUT re-staging — scanning the working tree would report "clean"
    while `git commit` still commits the original malicious staged blob."""
    result = subprocess.run(
        ["git", "cat-file", "-p", f":{path.as_posix()}"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def classify(cp: int) -> tuple[str, str] | None:
    """Return (category, label) for a codepoint of interest, else None."""
    if cp in BIDI_BLOCK:
        return ("bidi", BIDI_BLOCK[cp])
    if cp in ZWSP_FIXABLE:
        return ("zwsp", ZWSP_FIXABLE[cp])
    if cp in REPORT_ONLY_NEVER_FIX:
        return ("report_only", REPORT_ONLY_NEVER_FIX[cp])
    for lo, hi, label in REPORT_ONLY_NEVER_FIX_RANGES:
        if lo <= cp <= hi:
            return ("report_only", label)
    if cp == BOM:
        return ("bom", "BOM")
    return None


def scan_file(path: Path) -> list[dict]:
    findings: list[dict] = []
    if staged_is_symlink(path):
        # A staged symlink's blob content is just the target path string, not
        # the target file's content — scan_bytes() would read the wrong thing
        # entirely if we followed it (either via read_bytes() on the working
        # tree, or by treating the resolved target as this file's content).
        # The target path text itself is not a realistic watermark vector.
        return findings
    raw = staged_blob_bytes(path)
    if raw is None:
        return findings
    return scan_bytes(path, raw)


def scan_bytes(path: Path, raw: bytes) -> list[dict]:
    findings = []
    if len(raw) > MAX_FILE_SIZE:
        return findings
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return findings  # UTF-16 BOM — not our target, skip entirely
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return findings  # not UTF-8 text, not in scope
    for line_no, line in enumerate(text.splitlines(), start=1):
        for col, ch in enumerate(line, start=1):
            cp = ord(ch)
            result = classify(cp)
            if result is None:
                continue
            category, label = result
            context = line[max(0, col - 6) : col + 5]
            findings.append(
                {
                    "file": str(path),
                    "line": line_no,
                    "col": col,
                    "codepoint": f"U+{cp:04X}",
                    "label": label,
                    "category": category,
                    "context": context,
                }
            )
    return findings


def apply_fix(path: Path, findings: list[dict]) -> bool:
    """Strip only zwsp/bom findings that are safe per policy. Atomic write."""
    fixable_categories = {"zwsp"}
    if path.suffix in BOM_FIXABLE_EXTENSIONS:
        fixable_categories.add("bom")
    to_strip = {f["codepoint"] for f in findings if f["category"] in fixable_categories}
    if not to_strip:
        return False
    try:
        raw = path.read_bytes()
    except OSError:
        return False
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    strip_chars = {int(cp[2:], 16) for cp in to_strip}
    new_text = "".join(ch for ch in text if ord(ch) not in strip_chars)
    if new_text == text:
        return False
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(new_text, encoding="utf-8")
    tmp.replace(path)
    print(f"  fixed: {path}  (undo: git checkout -- {path}; re-stage: git add {path})")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Manually strip zero-width-space/BOM findings (never bidi, "
        "never ZWNJ/ZWJ/VS, never non-.py/.js/.ts for BOM).",
    )
    args = parser.parse_args()

    files = staged_files()
    all_findings: list[dict] = []
    for f in files:
        # No f.exists() gate here: detection reads the staged git blob (via
        # scan_file -> staged_blob_bytes), which exists independently of the
        # working-tree file. --fix still needs the working-tree file present.
        findings = scan_file(f)
        all_findings.extend(findings)

    if not all_findings:
        print("watermark-scan: no hidden/invisible characters found in staged files.")
        return 0

    by_file: dict[str, list[dict]] = {}
    for finding in all_findings:
        by_file.setdefault(finding["file"], []).append(finding)

    print(f"watermark-scan: {len(all_findings)} finding(s) in {len(by_file)} file(s)")
    hard_block = False
    for file_str, findings in by_file.items():
        print(f"\n{file_str}")
        for f in findings:
            marker = " [BLOCKING]" if f["category"] == "bidi" else ""
            if f["category"] == "bidi":
                hard_block = True
            print(
                f"  {f['line']}:{f['col']}  {f['codepoint']} ({f['label']})"
                f"  ctx={f['context']!r}{marker}"
            )
        if args.fix:
            apply_fix(Path(file_str), findings)

    if hard_block:
        print(
            "\nBidi/directional override characters found — this is the Trojan Source "
            "(CVE-2021-42574) attack signature. Never auto-fixed. Investigate manually."
        )

    if args.fix:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
