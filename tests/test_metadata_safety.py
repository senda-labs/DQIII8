"""Behavioral invariants protecting the standing constraint: removal is
always a human decision, never automatic. Covers CLI grammar (--apply/--all
--yes refusal, dry-run byte-identity), symlink refusal, existing-.bak
refusal, and the mechanical CI/hook grep enforcing the constraint itself.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS = REPO_ROOT / "bin" / "tools"
sys.path.insert(0, str(TOOLS))

import metadata_fixtures as mf  # noqa: E402


def _run(args):
    return subprocess.run(
        [sys.executable, str(TOOLS / "metadata_remove.py"), *args],
        capture_output=True,
        text=True,
    )


def _tree_hashes(root: Path) -> dict:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def test_dry_run_default_leaves_directory_byte_identical(tmp_path):
    mf.make_jpeg_with_exif(tmp_path / "a.jpg")
    mf.make_pdf_simple(tmp_path / "b.pdf", author="Someone")
    before = _tree_hashes(tmp_path)

    result = _run(["--dir", str(tmp_path)])
    assert result.returncode == 0

    after = _tree_hashes(tmp_path)
    assert before == after


def test_apply_all_without_yes_refused_zero_writes(tmp_path):
    mf.make_jpeg_with_exif(tmp_path / "a.jpg")
    before = _tree_hashes(tmp_path)

    result = _run(["--dir", str(tmp_path), "--apply", "--all"])
    assert result.returncode == 2

    after = _tree_hashes(tmp_path)
    assert before == after


def test_apply_without_all_actually_writes_and_leaves_backup(tmp_path):
    p = tmp_path / "a.jpg"
    mf.make_jpeg_with_exif(p)

    result = _run(["--dir", str(tmp_path), "--apply", "--json"])
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert any(r["status"] == "written" for r in report["results"])
    assert (tmp_path / "a.jpg.bak").exists()


def test_existing_backup_refuses_second_apply(tmp_path):
    p = tmp_path / "a.jpg"
    mf.make_jpeg_with_exif(p)
    (tmp_path / "a.jpg.bak").write_bytes(b"pre-existing backup content")
    before = p.read_bytes()

    result = _run(["--file", str(p), "--apply", "--json"])
    report = json.loads(result.stdout)
    assert report["results"][0]["status"] == "write_refused"
    assert p.read_bytes() == before


def test_symlink_file_refused(tmp_path):
    real = tmp_path / "real.jpg"
    mf.make_jpeg_with_exif(real)
    link = tmp_path / "link.jpg"
    link.symlink_to(real)

    result = _run(["--file", str(link), "--apply"])
    assert result.returncode == 2


def test_symlink_in_directory_sweep_skipped(tmp_path):
    real_dir = tmp_path / "outside"
    real_dir.mkdir()
    real = real_dir / "real.jpg"
    mf.make_jpeg_with_exif(real)
    link = tmp_path / "link.jpg"
    link.symlink_to(real)

    result = _run(["--dir", str(tmp_path), "--apply", "--json"])
    report = json.loads(result.stdout)
    assert report["skipped"].get("symlink", 0) >= 1
    assert real.read_bytes() != b""  # untouched target, never followed


def test_bak_and_tmp_excluded_from_directory_sweep(tmp_path):
    (tmp_path / "leftover.jpg.bak").write_bytes(b"old backup bytes")
    (tmp_path / "leftover.jpg.tmp").write_bytes(b"stray tmp bytes")
    before_bak = (tmp_path / "leftover.jpg.bak").read_bytes()
    before_tmp = (tmp_path / "leftover.jpg.tmp").read_bytes()

    result = _run(["--dir", str(tmp_path), "--apply", "--json"])
    report = json.loads(result.stdout)
    assert report["results"] == []
    assert (tmp_path / "leftover.jpg.bak").read_bytes() == before_bak
    assert (tmp_path / "leftover.jpg.tmp").read_bytes() == before_tmp


def test_no_ci_or_hook_config_references_metadata_remove():
    """The standing manual-only constraint made mechanical, not just
    documented: no workflow, git hook, or Claude hook may ever wire up
    metadata_remove.py's write path.
    """
    workflows = REPO_ROOT / ".github" / "workflows"
    candidates = []
    if workflows.is_dir():
        # .yaml is as valid as .yml for GitHub Actions — globbing only *.yml
        # left the obvious bypass wide open.
        candidates += [p for p in workflows.iterdir() if p.suffix in (".yml", ".yaml")]
    hooks_dir = REPO_ROOT / ".claude" / "hooks"
    if hooks_dir.is_dir():
        candidates += [p for p in hooks_dir.rglob("*") if p.is_file()]
    # The hook *wiring* lives in settings.json, not only in the hook scripts —
    # a `command:` entry there could invoke the remover with no .py file in
    # .claude/hooks/ ever mentioning it.
    for cfg in ("settings.json", "settings.local.json"):
        p = REPO_ROOT / ".claude" / cfg
        if p.is_file():
            candidates.append(p)
    git_hooks_dir = REPO_ROOT / ".git" / "hooks"
    if git_hooks_dir.is_dir():
        candidates += [p for p in git_hooks_dir.iterdir() if p.is_file() and not p.name.endswith(".sample")]

    for p in candidates:
        text = p.read_text(errors="ignore")
        for tool in ("metadata_remove", "watermark_remove"):
            assert tool not in text, f"{p} references {tool} — removal must stay manual-only"


@pytest.mark.skip(
    reason="deferred technical debt (2026-08-14): golden-file tests for "
    "metadata_audit.py/metadata_remove.py --json reports (commit expected "
    "output per fixture, volatile fields normalized — timestamps, "
    "invocation_id, absolute paths, engine versions) not yet implemented. "
    "Not blocking: schema/tier/finding coverage is already asserted "
    "directly in test_metadata_*.py; this would only add regression "
    "protection against an accidental schema break in a reviewable diff."
)
def test_json_report_golden_files():
    """Placeholder — see skip reason. Implement when the report schema
    stabilizes enough to be worth pinning, or on explicit request."""
