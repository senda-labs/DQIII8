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


GOLDEN_DIR = REPO_ROOT / "tests" / "golden"

GOLDEN_FIXTURES = {
    # name: (make_fixture, filename, tool, base_args, expected_returncode)
    # metadata_audit.py exits 1 when findings exist (see _exit_code()) —
    # that's a deliberate signal, not a failure, since every fixture here
    # is built to have findings.
    "audit_jpeg_exif": (mf.make_jpeg_with_exif, "a.jpg", TOOLS / "metadata_audit.py", ["--file"], 1),
    "audit_pdf_simple": (mf.make_pdf_simple, "a.pdf", TOOLS / "metadata_audit.py", ["--file"], 1),
    "audit_docx_simple": (mf.make_docx_simple, "a.docx", TOOLS / "metadata_audit.py", ["--file"], 1),
    "remove_jpeg_exif_dry_run": (mf.make_jpeg_with_exif, "a.jpg", TOOLS / "metadata_remove.py", ["--file"], 0),
    "remove_pdf_simple_dry_run": (mf.make_pdf_simple, "a.pdf", TOOLS / "metadata_remove.py", ["--file"], 0),
}


def _normalize(report: dict, tmp_path: Path) -> dict:
    """Strip fields that legitimately vary between runs/environments
    (timestamps, invocation ids, absolute tmp paths, engine versions) so the
    golden comparison only catches real schema/shape changes."""
    text = json.dumps(report)
    text = text.replace(str(tmp_path), "<TMPDIR>")
    normalized = json.loads(text)
    normalized.pop("generated_at", None)
    normalized.pop("invocation_id", None)
    for engine, version in list(normalized.get("engines", {}).items()):
        if version != "absent":
            normalized["engines"][engine] = "<VERSION>"
    return normalized


def test_json_report_golden_files(tmp_path):
    """Pin metadata_audit.py/metadata_remove.py --json output shape per
    fixture. A diff here means the report schema changed — update the
    golden file deliberately (and note the schema bump) if the change is
    intentional; a silent break is exactly what this guards against."""
    for name, (make_fixture, filename, tool, base_args, expected_rc) in GOLDEN_FIXTURES.items():
        target = tmp_path / name / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        make_fixture(target)

        result = subprocess.run(
            [sys.executable, str(tool), *base_args, str(target), "--json"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == expected_rc, f"{name}: rc={result.returncode} {result.stderr}"
        report = json.loads(result.stdout)
        normalized = _normalize(report, target.parent)

        golden_path = GOLDEN_DIR / f"{name}.json"
        assert golden_path.exists(), (
            f"missing golden file {golden_path} — run the fixture generation "
            f"once and commit its output deliberately"
        )
        expected = json.loads(golden_path.read_text())
        assert normalized == expected, f"{name}: report shape drifted from golden file"
