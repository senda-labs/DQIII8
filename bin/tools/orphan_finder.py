#!/usr/bin/env python3
"""orphan_finder.py — Report which scripts in bin/ are referenced by nothing.

Checks: crontab, CLAUDE.md, .claude/agents/, .claude/skills/, bin/ imports,
        .claude/settings.json, bin/**/*.sh (j.sh, nightly.sh, etc.)
"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BIN = ROOT / "bin"


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _crontab() -> str:
    try:
        return subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True, timeout=5
        ).stdout
    except Exception:
        return ""


def _shell_scripts() -> str:
    """Concatenate all *.sh files under bin/ and scripts/ (if present)."""
    text = ""
    for pattern in ["bin/**/*.sh", "scripts/**/*.sh"]:
        for f in ROOT.glob(pattern):
            if "archive" not in f.parts and "venv" not in f.parts:
                text += _text(f) + "\n"
    return text


def _collect_corpus() -> dict[str, str]:
    """Return named text blobs to search against."""
    corpus: dict[str, str] = {
        "cron": _crontab(),
        "claude.md": _text(ROOT / "CLAUDE.md"),
        "settings": _text(ROOT / ".claude" / "settings.json"),
        "shell": _shell_scripts(),
    }
    agents_text = ""
    for f in (ROOT / ".claude" / "agents").glob("*.md"):
        agents_text += _text(f) + "\n"
    corpus["agents"] = agents_text

    skills_text = ""
    for f in (ROOT / ".claude" / "skills").rglob("SKILL.md"):
        skills_text += _text(f) + "\n"
    corpus["skills"] = skills_text

    bin_text = ""
    for f in BIN.rglob("*.py"):
        if "__pycache__" not in f.parts and "venv" not in f.parts:
            bin_text += _text(f) + "\n"
    corpus["bin"] = bin_text

    return corpus


def main() -> None:
    corpus = _collect_corpus()
    scripts = sorted(
        f
        for f in BIN.rglob("*.py")
        if "__pycache__" not in f.parts and "venv" not in f.parts
    )

    keys = ["cron", "claude.md", "agents", "skills", "bin", "shell", "settings"]
    col_w = 9

    header = f"{'Script':<55} " + " ".join(f"{k:>{col_w}}" for k in keys) + "  VERDICT"
    print(header)
    print("-" * len(header))

    orphans = []
    for script in scripts:
        rel = str(script.relative_to(ROOT))
        name = script.stem  # filename without .py

        hits = {}
        for key, text in corpus.items():
            if key == "bin":
                # Only count if a *different* file imports or references this one
                other_text = ""
                for f in BIN.rglob("*.py"):
                    if (
                        f != script
                        and "__pycache__" not in f.parts
                        and "venv" not in f.parts
                    ):
                        other_text += _text(f)
                found = name in other_text or rel in other_text
            else:
                found = name in text or rel in text
            hits[key] = found

        total = sum(hits.values())
        verdict = "USED" if total > 0 else "ORPHAN"
        if verdict == "ORPHAN":
            orphans.append(rel)

        marks = " ".join(
            f"{'Y':>{col_w}}" if hits[k] else f"{'·':>{col_w}}" for k in keys
        )
        flag = "  <-- ORPHAN" if verdict == "ORPHAN" else ""
        print(f"{rel:<55} {marks}{flag}")

    print()
    print(f"Total scripts: {len(scripts)} | Orphans: {len(orphans)}")
    if orphans:
        print("\nOrphans:")
        for o in orphans:
            print(f"  {o}")


if __name__ == "__main__":
    main()
