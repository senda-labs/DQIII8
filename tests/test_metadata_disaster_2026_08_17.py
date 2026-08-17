"""Regression tests for the 2026-08-17 disaster-scenario / operational-failure-mode
testing pass (see database/audit_reports/2026-08-17-metadata-watermark-disaster-testing.md).

Each test pins one of the three bugs found in that pass that were not already
covered by tests/test_metadata_remediation.py's ENOSPC regression test:

  - Fix B: metadata_remove.py --file mode had no per-file size ceiling.
  - Fix C/E: watermark_remove.py had no per-file size ceiling in either --dir
    or --file mode.
  - Fix D: watermark_remove.py --file pointed at a symlink silently fell
    through to a "no hidden/invisible characters found" false clean instead
    of refusing, on a target that in fact had real findings.

All three were confirmed live against real oversized/symlinked fixtures before
being pinned here as fast, tmp_path-scale tests using --max-bytes overrides
rather than actually writing gigabyte-scale files.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS = REPO_ROOT / "bin" / "tools"
sys.path.insert(0, str(TOOLS))

import metadata_fixtures as mf  # noqa: E402


def _run(tool: str, args):
    return subprocess.run(
        [sys.executable, str(TOOLS / tool), *args], capture_output=True, text=True
    )


# ---------------------------------------------------------- Fix B (metadata_remove --file) ---


def test_metadata_remove_file_mode_refuses_oversized_file(tmp_path):
    img = tmp_path / "a.jpg"
    mf.make_jpeg_with_exif(img)
    before = img.read_bytes()

    # --max-bytes set below the fixture's real size stands in for "pathologically
    # large file vs. the 2GiB default ceiling" without writing gigabytes to disk.
    r = _run(
        "metadata_remove.py",
        ["--file", str(img), "--apply", "--max-bytes", "1"],
    )

    assert r.returncode == 2
    assert "exceeding --max-bytes" in r.stderr
    assert img.read_bytes() == before
    assert not (tmp_path / "a.jpg.bak").exists()
    assert not (tmp_path / "a.jpg.tmp").exists()


def test_metadata_remove_file_mode_allows_file_under_ceiling(tmp_path):
    img = tmp_path / "a.jpg"
    mf.make_jpeg_with_exif(img)

    r = _run(
        "metadata_remove.py",
        ["--file", str(img), "--max-bytes", str(10 * 1024 * 1024)],
    )

    assert r.returncode == 0
    assert "exceeding --max-bytes" not in r.stderr


# ---------------------------------------------------------- Fix C/E (watermark_remove size) ---


def test_watermark_remove_file_mode_refuses_oversized_file(tmp_path, monkeypatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location("watermark_remove", TOOLS / "watermark_remove.py")
    watermark_remove = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(watermark_remove)

    p = tmp_path / "doc.txt"
    p.write_text("hello\u200bworld", encoding="utf-8")
    before = p.read_bytes()

    monkeypatch.setattr(watermark_remove, "MAX_FILE_BYTES", 1)
    monkeypatch.setattr(sys, "argv", ["watermark_remove.py", "--file", str(p), "--apply"])

    rc = watermark_remove.main()

    assert rc == 2
    assert p.read_bytes() == before
    assert not (tmp_path / "doc.txt.bak").exists()


def test_watermark_remove_dir_mode_skips_oversized_file(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("watermark_remove", TOOLS / "watermark_remove.py")
    watermark_remove = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(watermark_remove)

    big = tmp_path / "big.txt"
    big.write_text("hello\u200bworld", encoding="utf-8")
    watermark_remove.MAX_FILE_BYTES = 1  # smaller than the fixture, forces the skip path

    files, skip_counts, truncated = watermark_remove.collect_files(tmp_path, None)

    assert big not in files
    assert skip_counts.get("oversized") == 1
    assert truncated is None


# ---------------------------------------------------------- Fix D (watermark_remove --file symlink) ---


def test_watermark_remove_file_mode_refuses_symlink_instead_of_false_clean(tmp_path, capsys):
    import importlib.util

    spec = importlib.util.spec_from_file_location("watermark_remove", TOOLS / "watermark_remove.py")
    watermark_remove = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(watermark_remove)

    real = tmp_path / "real.txt"
    real.write_text("hello\u200bworld has a zero-width space", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(real)

    watermark_remove_argv_backup = sys.argv
    sys.argv = ["watermark_remove.py", "--file", str(link), "--apply"]
    try:
        rc = watermark_remove.main()
    finally:
        sys.argv = watermark_remove_argv_backup

    out = capsys.readouterr()
    # Before the fix, this printed "no hidden/invisible characters found" and
    # exited 0 — a false clean on a target that demonstrably has a finding.
    assert rc == 2
    assert "no hidden/invisible characters found" not in out.out
    assert "refusing symlinked --file target" in out.err
    # The real file must be untouched — refusal, not a silent skip-and-report-clean.
    assert "\u200b" in real.read_text(encoding="utf-8")
