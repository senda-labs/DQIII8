#!/usr/bin/env python3
"""
DQIII8 — Lessons Consolidator
Groups lessons.md entries by keyword. When a keyword has >= 3 entries,
compresses them into a pattern line and archives originals.

Usage:
    python3 bin/lessons_consolidator.py           # apply consolidation
    python3 bin/lessons_consolidator.py --dry-run # stats only
"""

import argparse
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

DQIII8_ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
LESSONS_FILE = DQIII8_ROOT / "tasks" / "lessons.md"
ARCHIVE_DIR = DQIII8_ROOT / "tasks" / "lessons_archive"
MAX_LESSONS_LINES = 100
CONSOLIDATE_THRESHOLD = 3


def parse_lessons(lines: list[str]) -> tuple[dict[str, list[str]], list[str]]:
    """
    Parse lesson lines into {keyword: [lines]} and orphan lines (no keyword tag).
    Expects format: - [YYYY-MM-DD] [KEYWORD] text
    or:             - [YYYY-MM-DD] text (no keyword → orphan)
    """
    keyword_map: dict[str, list[str]] = defaultdict(list)
    orphans: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("-"):
            orphans.append(line)
            continue
        # Try to extract keyword tag: - [date] [KEYWORD] ...
        m = re.match(r"^-\s*\[\d{4}-\d{2}-\d{2}\]\s*\[([A-Z0-9_\-]+)\]", stripped)
        if m:
            keyword = m.group(1).lower()
            keyword_map[keyword].append(stripped)
        else:
            orphans.append(line)

    return dict(keyword_map), orphans


def main() -> None:
    parser = argparse.ArgumentParser(description="DQIII8 lessons consolidator")
    parser.add_argument("--dry-run", action="store_true", help="Stats only, no changes")
    args = parser.parse_args()

    if not LESSONS_FILE.exists():
        print("[lessons_consolidator] lessons.md not found — skipping")
        sys.exit(0)

    lines = LESSONS_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
    lesson_lines = [l for l in lines if l.strip().startswith("-")]
    non_lesson = [l for l in lines if not l.strip().startswith("-")]

    keyword_map, orphans = parse_lessons(lesson_lines)

    to_consolidate = {k: v for k, v in keyword_map.items() if len(v) >= CONSOLIDATE_THRESHOLD}
    to_keep_as_is = {k: v for k, v in keyword_map.items() if len(v) < CONSOLIDATE_THRESHOLD}

    total_before = sum(len(v) for v in keyword_map.values()) + len(orphans)
    archived_count = sum(len(v) for v in to_consolidate.values())
    pattern_lines_count = len(to_consolidate)

    print(f"[lessons_consolidator] Total lesson lines: {total_before}")
    print(
        f"[lessons_consolidator] Keywords with >= {CONSOLIDATE_THRESHOLD} entries: {len(to_consolidate)}"
    )
    print(f"[lessons_consolidator] Lines to archive: {archived_count}")
    print(f"[lessons_consolidator] Pattern lines to create: {pattern_lines_count}")

    if args.dry_run:
        for kw, entries in to_consolidate.items():
            print(f"  [{kw}] {len(entries)} entries → 1 pattern line")
        print("\n[lessons_consolidator] Dry run — no changes applied.")
        sys.exit(0)

    # Archive consolidated entries
    ARCHIVE_DIR.mkdir(exist_ok=True)
    month_key = datetime.now().strftime("%Y-%m")
    archive_file = ARCHIVE_DIR / f"{month_key}.md"

    archive_lines = []
    if archive_file.exists():
        archive_lines = archive_file.read_text(encoding="utf-8").splitlines(keepends=True)

    new_archive_content = "".join(archive_lines)
    for kw, entries in to_consolidate.items():
        new_archive_content += f"\n## {kw} (archived {month_key})\n"
        for entry in entries:
            new_archive_content += entry + "\n"

    archive_file.write_text(new_archive_content, encoding="utf-8")

    # Build new lessons.md
    now_str = datetime.now().strftime("%Y-%m-%d")
    new_lesson_lines = list(orphans)

    # Keep non-consolidated keywords as-is
    for kw, entries in to_keep_as_is.items():
        new_lesson_lines.extend(e + "\n" for e in entries)

    # Add pattern lines for consolidated keywords
    for kw, entries in to_consolidate.items():
        most_recent = entries[-1]  # last = most recent
        # Extract the text part after [KEYWORD]
        text_match = re.match(r"^-\s*\[[\d-]+\]\s*\[[^\]]+\]\s*(.*)", most_recent)
        text = text_match.group(1) if text_match else most_recent[2:]
        pattern_line = (
            f"- [{now_str}] [PATTERN:{kw.upper()}] " f"{len(entries)} ocurrencias: {text.strip()}\n"
        )
        new_lesson_lines.append(pattern_line)

    # Rebuild with header lines preserved
    rebuilt = "".join(non_lesson[:3]) + "".join(new_lesson_lines[-MAX_LESSONS_LINES:])
    LESSONS_FILE.write_text(rebuilt, encoding="utf-8")

    after_count = len(new_lesson_lines)
    print(
        f"[lessons_consolidator] Done — {total_before} → {after_count} lines, "
        f"{archived_count} archived to {archive_file.name}"
    )


if __name__ == "__main__":
    main()
