#!/usr/bin/env python3
"""Scan staged files for invisible/hidden Unicode characters (watermark-style artifacts):
bidi overrides, Unicode Tag block (ASCII smuggling), line/paragraph separators, zero-width
space, invisible math operators, deprecated invisible format chars, soft hyphen, BOM.
Report-only for ZWNJ/ZWJ/variation selectors (legitimate in some scripts and emoji
sequences) — a ZWJ/VS immediately following an emoji-range codepoint is treated as a
legitimate emoji sequence and not flagged at all, since that is the overwhelming majority
of real-world occurrences and flagging it trains `--no-verify` into muscle memory.

Scope is deliberately narrow: only files staged for commit
(`git diff --cached --diff-filter=d --name-only -z`). Never walks directories, never
touches untracked or gitignored paths — this by construction excludes client data
under my-projects/ and any large research datasets. Detection reads each file's
STAGED git index blob (`git cat-file -p :<path>`), not the working-tree copy —
the two can diverge (stage malicious content, then revert the working tree without
re-staging) and only the index content is what actually gets committed. Staged
symlinks are skipped: a symlink's blob content is the target path string, not the
target file's content, so following it would scan the wrong thing entirely.

Every skip (oversized file, symlink, unreadable blob, undecodable text) is counted
and reported in the summary line — never silent, since a silent skip is a trivial
bypass (pad a file past the size ceiling, or save it non-UTF-8/UTF-16). UTF-16
(BOM-prefixed) content is decoded and scanned like any other text, not skipped —
bidi/tag characters carry through UTF-16 fine, so blind-skipping it was itself a
bypass.

Default mode is report-only and blocking (exit 1 if anything unresolved remains).
--fix is a manual, opt-in, human-run flag that strips only the categories it can
safely strip; anything it can't (bidi, tag, linesep, report_only) still exits 1
even under --fix — it was previously possible for --fix to exit 0 while a bidi
override was still sitting in the file untouched.

Usage:
    python3 bin/tools/watermark_scan.py [--fix]
"""

from __future__ import annotations

import argparse
import os
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
    0x200E: "LRM",
    0x200F: "RLM",
}

# Unicode Tag block — payload-carrying invisible characters (each tag codepoint
# mirrors an ASCII byte via +0xE0000 offset). Used for "ASCII smuggling": a
# whole hidden instruction/payload can ride inside otherwise-normal-looking
# text with zero visible trace. Hard-block like bidi — never auto-fixable,
# since silently stripping would destroy evidence of an active payload.
TAG_BLOCK_RANGES = [(0xE0000, 0xE007F, "TAG")]

# Line/paragraph separator — can desync line-based tooling (including this
# scanner's own line numbering) from git's, and hides content from casual
# line-oriented review. Structural risk profile like bidi: hard-block, never
# auto-fixable (semantics of removal are ambiguous — could be a real line break).
LINE_SEP_BLOCK = {0x2028: "LSEP", 0x2029: "PSEP"}

# Invisible math operators — no legitimate use in source code or prose.
INVISIBLE_MATH_FIXABLE = {
    0x2060: "WJ",
    0x2061: "FUNC-APP",
    0x2062: "INVIS-TIMES",
    0x2063: "INVIS-SEP",
    0x2064: "INVIS-PLUS",
}

# Deprecated invisible format characters + soft hyphen — no legitimate rendered
# use in code/docs, and soft hyphen in particular is one of the most common
# real-world invisible carriers (invisible unless the line wraps at that point).
INVISIBLE_CTRL_FIXABLE = {
    0x00AD: "SHY",
    0x206A: "ISS",
    0x206B: "ASS",
    0x206C: "IAFS",
    0x206D: "AAFS",
    0x206E: "NADS",
    0x206F: "NODS",
}

# Zero-width space: only real category safe to auto-fix, and only manually.
ZWSP_FIXABLE = {0x200B: "ZWSP"}

# Legitimate in Persian/Hindi text (ZWNJ) and emoji presentation/ZWJ sequences
# (ZWJ, VS16, ideographic variation selectors) — but ZWJ/VS immediately after
# an emoji-range codepoint is suppressed entirely (see _is_emoji_context below)
# rather than reported, since that covers the overwhelming majority of real
# occurrences. What's left here still fires for non-emoji-context uses, where
# there is no reliable way to tell "watermark" from "correct use" — report
# only, never touched by --fix.
REPORT_ONLY_NEVER_FIX = {
    0x200C: "ZWNJ",
    0x200D: "ZWJ",
    0x180E: "MVS",
    0x3164: "HANGUL-FILLER",
    0x115F: "HANGUL-CHOSEONG-FILLER",
    0xFFF9: "IAA-START",
    0xFFFA: "IAA-SEP",
    0xFFFB: "IAA-END",
    0x2800: "BRAILLE-BLANK",
}
REPORT_ONLY_NEVER_FIX_RANGES = [
    (0xFE00, 0xFE0F, "VS1-16"),
    (0xE0100, 0xE01EF, "VS17-256"),
]

# Codepoint ranges treated as a plausible "emoji base" for context suppression:
# a ZWJ or variation selector immediately following one of these is assumed to
# be a legitimate emoji sequence, not a watermark carrier. Heuristic, not a
# full emoji-property table — false negatives here just mean "still reported",
# never "silently stripped".
_EMOJI_BASE_RANGES = [
    (0x1F1E6, 0x1F1FF),  # regional indicators
    (0x1F300, 0x1FAFF),  # misc pictographs / emoticons / transport / symbols
    (0x2100, 0x27BF),    # letterlike symbols through dingbats (incl. info/check marks)
    (0x2B00, 0x2BFF),    # misc symbols and arrows
    (0x0023, 0x0023),    # '#'  (keycap base)
    (0x002A, 0x002A),    # '*'  (keycap base)
    (0x0030, 0x0039),    # '0'-'9' (keycap base)
]
_EMOJI_CONTEXT_LABELS = {"ZWJ", "VS1-16", "VS17-256"}

BOM = 0xFEFF
BOM_FIXABLE_EXTENSIONS = {".py", ".js", ".ts"}


def _is_emoji_base(cp: int) -> bool:
    return any(lo <= cp <= hi for lo, hi in _EMOJI_BASE_RANGES)


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


def staged_symlinks(files: list[Path]) -> set[str]:
    """Batched symlink check (one `git ls-files` call for all staged files,
    instead of one subprocess per file)."""
    if not files:
        return set()
    out = subprocess.run(
        ["git", "ls-files", "-s", "-z", "--"] + [f.as_posix() for f in files],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        print(f"watermark-scan: warning: git ls-files failed: {out.stderr.strip()}", file=sys.stderr)
        return set()
    symlinks = set()
    for entry in out.stdout.split("\0"):
        if not entry:
            continue
        mode_part, _, path_part = entry.partition("\t")
        if mode_part.startswith("120000"):
            symlinks.add(path_part)
    return symlinks


def staged_is_symlink(path: Path) -> bool:
    """True if the staged (index) entry for this path is a symlink (mode 120000).
    Kept for single-file/library callers; `main()` uses the batched staged_symlinks()."""
    return path.as_posix() in staged_symlinks([path])


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


def ref_diff_files(base: str, target: str) -> list[Path]:
    """CI-mode equivalent of staged_files(): files changed between BASE and
    TARGET (merge-base diff, like GitHub's PR diff), instead of the git index."""
    out = subprocess.run(
        ["git", "diff", "--diff-filter=d", "--name-only", "-z", f"{base}...{target}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        print(f"watermark-scan: git diff {base}...{target} failed: {out.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return [Path(p) for p in out.stdout.split("\0") if p]


def ref_symlinks(files: list[Path], target: str) -> set[str]:
    """CI-mode equivalent of staged_symlinks(): symlink check against TARGET's
    tree instead of the index (there is no index to inspect in a CI checkout)."""
    if not files:
        return set()
    out = subprocess.run(
        ["git", "ls-tree", "-z", "-r", target, "--"] + [f.as_posix() for f in files],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        print(f"watermark-scan: warning: git ls-tree failed: {out.stderr.strip()}", file=sys.stderr)
        return set()
    symlinks = set()
    for entry in out.stdout.split("\0"):
        if not entry:
            continue
        meta, _, path_part = entry.partition("\t")
        mode = meta.split(" ", 1)[0] if meta else ""
        if mode.startswith("120000"):
            symlinks.add(path_part)
    return symlinks


def ref_blob_bytes(path: Path, target: str) -> bytes | None:
    """CI-mode equivalent of staged_blob_bytes(): read the file's content at
    TARGET's commit tree instead of the git index."""
    result = subprocess.run(
        ["git", "cat-file", "-p", f"{target}:{path.as_posix()}"],
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
    for lo, hi, label in TAG_BLOCK_RANGES:
        if lo <= cp <= hi:
            return ("tag", label)
    if cp in LINE_SEP_BLOCK:
        return ("linesep", LINE_SEP_BLOCK[cp])
    if cp in ZWSP_FIXABLE:
        return ("zwsp", ZWSP_FIXABLE[cp])
    if cp in INVISIBLE_MATH_FIXABLE:
        return ("invis_math", INVISIBLE_MATH_FIXABLE[cp])
    if cp in INVISIBLE_CTRL_FIXABLE:
        return ("invisible_ctrl", INVISIBLE_CTRL_FIXABLE[cp])
    if cp in REPORT_ONLY_NEVER_FIX:
        return ("report_only", REPORT_ONLY_NEVER_FIX[cp])
    for lo, hi, label in REPORT_ONLY_NEVER_FIX_RANGES:
        if lo <= cp <= hi:
            return ("report_only", label)
    if cp == BOM:
        return ("bom", "BOM")
    return None


def _decode(raw: bytes) -> tuple[str | None, str]:
    """Returns (text, reason). text is None iff the file was skipped; reason is
    'ok' | 'too-large' | 'utf16-decode-error' | 'non-utf8'. UTF-16 (BOM-prefixed)
    content is decoded and scanned, not blind-skipped — bidi/tag chars survive
    UTF-16 fine, so skipping it was a real bypass."""
    if len(raw) > MAX_FILE_SIZE:
        return None, "too-large"
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return raw.decode("utf-16"), "ok"
        except UnicodeDecodeError:
            return None, "utf16-decode-error"
    try:
        return raw.decode("utf-8"), "ok"
    except UnicodeDecodeError:
        return None, "non-utf8"


def scan_file(path: Path) -> list[dict]:
    findings: list[dict] = []
    if staged_is_symlink(path):
        # A staged symlink's blob content is just the target path string, not
        # the target file's content — scan_bytes() would read the wrong thing
        # entirely if we followed it. The target path text itself is not a
        # realistic watermark vector.
        return findings
    raw = staged_blob_bytes(path)
    if raw is None:
        return findings
    return scan_bytes(path, raw)


def scan_bytes(path: Path, raw: bytes) -> list[dict]:
    findings: list[dict] = []
    text, reason = _decode(raw)
    if text is None:
        return findings
    # Split on '\n' only — NOT str.splitlines(), which also breaks on
    # \x1c-\x1e/\x85/U+2028/U+2029 and would silently swallow the very
    # line/paragraph-separator characters this scanner needs to detect,
    # desyncing reported line numbers from git's in the process.
    for line_no, line in enumerate(text.split("\n"), start=1):
        for col, ch in enumerate(line, start=1):
            cp = ord(ch)
            result = classify(cp)
            if result is None:
                continue
            category, label = result
            if category == "report_only" and label in _EMOJI_CONTEXT_LABELS:
                prev_ch = line[col - 2] if col - 2 >= 0 else None
                if prev_ch is not None and _is_emoji_base(ord(prev_ch)):
                    continue  # legitimate emoji sequence, not a watermark carrier
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


def _fixable_categories(path: Path) -> set[str]:
    cats = {"zwsp", "invis_math", "invisible_ctrl"}
    if path.suffix in BOM_FIXABLE_EXTENSIONS:
        cats.add("bom")
    return cats


def apply_fix(path: Path, findings: list[dict]) -> bool:
    """Strip only findings in a safe-to-strip category (see _fixable_categories).
    Atomic write; preserves the original file mode (a previous version silently
    dropped e.g. 0755 -> 0644 on every fix)."""
    fixable_categories = _fixable_categories(path)
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
    try:
        mode = path.stat().st_mode
    except OSError:
        mode = None
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(new_text, encoding="utf-8")
    if mode is not None:
        os.chmod(tmp, mode)
    tmp.replace(path)
    print(f"  fixed: {path}  (undo: git checkout -- {path}; re-stage: git add {path})")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Manually strip zero-width-space/invisible-math/invisible-ctrl/BOM "
        "findings (never bidi, tag, linesep, ZWNJ/ZWJ/VS, never non-.py/.js/.ts "
        "for BOM). Still exits 1 if anything outside those categories remains. "
        "Ignored (with a warning) in --base/CI mode — removal stays a human, "
        "local, git-staged-only action, never something CI does automatically.",
    )
    parser.add_argument(
        "--base",
        help="CI mode: scan files changed between BASE and --target (merge-base "
        "diff, like a PR diff) instead of the git staging area. Detection only.",
    )
    parser.add_argument("--target", default="HEAD", help="CI mode: the ref to read changed content from (default HEAD).")
    args = parser.parse_args()

    ci_mode = args.base is not None
    if ci_mode and args.fix:
        print("watermark-scan: --fix is ignored in --base/CI mode (detection only).", file=sys.stderr)
        args.fix = False

    if ci_mode:
        files = ref_diff_files(args.base, args.target)
        symlinks = ref_symlinks(files, args.target)
    else:
        files = staged_files()
        symlinks = staged_symlinks(files)

    skip_counts: dict[str, int] = {}
    file_findings: dict[str, list[dict]] = {}
    all_findings: list[dict] = []

    for f in files:
        if f.as_posix() in symlinks:
            skip_counts["symlink"] = skip_counts.get("symlink", 0) + 1
            continue
        raw = ref_blob_bytes(f, args.target) if ci_mode else staged_blob_bytes(f)
        if raw is None:
            skip_counts["unreadable"] = skip_counts.get("unreadable", 0) + 1
            continue
        text, reason = _decode(raw)
        if text is None:
            skip_counts[reason] = skip_counts.get(reason, 0) + 1
            continue
        findings = scan_bytes(f, raw)
        if findings:
            file_findings[str(f)] = findings
            all_findings.extend(findings)

    if skip_counts:
        parts = ", ".join(f"{k}={v}" for k, v in sorted(skip_counts.items()))
        print(f"watermark-scan: skipped {sum(skip_counts.values())} file(s): {parts}")

    if not all_findings:
        print("watermark-scan: no hidden/invisible characters found in staged files.")
        return 0

    print(f"watermark-scan: {len(all_findings)} finding(s) in {len(file_findings)} file(s)")
    hard_block = False
    unresolved = False
    for file_str, findings in file_findings.items():
        print(f"\n{file_str}")
        for f in findings:
            marker = " [BLOCKING]" if f["category"] in ("bidi", "tag", "linesep") else ""
            if f["category"] in ("bidi", "tag", "linesep"):
                hard_block = True
            print(
                f"  {f['line']}:{f['col']}  {f['codepoint']} ({f['label']})"
                f"  ctx={f['context']!r}{marker}"
            )
        if args.fix:
            apply_fix(Path(file_str), findings)
            fixable = _fixable_categories(Path(file_str))
            if any(f["category"] not in fixable for f in findings):
                unresolved = True
        else:
            unresolved = True  # nothing was fixed — every finding is still live

    if hard_block:
        print(
            "\nBidi/directional-override, Unicode Tag, or line/paragraph-separator "
            "characters found — Trojan Source (CVE-2021-42574), ASCII-smuggling, and "
            "line-desync attack signatures. Never auto-fixed. Investigate manually."
        )

    return 1 if unresolved else 0


if __name__ == "__main__":
    sys.exit(main())
