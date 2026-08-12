"""Tests for bin/tools/watermark_scan.py.

Covers one positive case per detectable category, explicit regression cases
for content that must never be flagged for auto-fix or mangled, and
regression cases for three real bypasses found under adversarial stress
testing (2026-08-12) and fixed: working-tree/index divergence (TOCTOU),
symlink content substitution, and non-ASCII filename quoting.

All fixture strings use chr(0x...) rather than raw literal codepoints, so
this source file itself never contains the invisible/hidden characters under
test (the pre-commit watermark-scan hook would otherwise correctly flag its
own test fixtures as findings).
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bin" / "tools"))

import watermark_scan as ws  # noqa: E402

ZWSP = chr(0x200B)
RLO = chr(0x202E)
ZWJ = chr(0x200D)
ZWNJ = chr(0x200C)
VS16 = chr(0xFE0F)
BOM = chr(0xFEFF)


def _git_repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    return tmp_path


def _stage(repo, relpath):
    subprocess.run(["git", "add", "--", relpath], cwd=repo, check=True)


def test_classify_bidi_blocks():
    category, label = ws.classify(0x202E)
    assert category == "bidi"
    assert label == "RLO"


def test_classify_zwsp_fixable():
    category, _ = ws.classify(0x200B)
    assert category == "zwsp"


def test_classify_bom():
    category, _ = ws.classify(0xFEFF)
    assert category == "bom"


def test_classify_zwnj_zwj_report_only_never_fix():
    assert ws.classify(0x200C)[0] == "report_only"
    assert ws.classify(0x200D)[0] == "report_only"


def test_classify_vs16_emoji_report_only():
    category, label = ws.classify(0xFE0F)
    assert category == "report_only"
    assert label == "VS1-16"


def test_classify_vs17_256_ideographic_report_only():
    category, label = ws.classify(0xE0100)
    assert category == "report_only"
    assert label == "VS17-256"


def test_classify_ordinary_char_is_none():
    assert ws.classify(ord("a")) is None


# --- scan_bytes(): pure content-classification logic, no git required ---


def test_scan_bytes_finds_zwsp(tmp_path):
    p = tmp_path / "watermarked.py"
    findings = ws.scan_bytes(p, f"x = 1{ZWSP}\n".encode("utf-8"))
    assert any(f["category"] == "zwsp" for f in findings)


def test_scan_bytes_finds_bidi_override(tmp_path):
    p = tmp_path / "trojan.py"
    findings = ws.scan_bytes(p, f"x = 1  # {RLO} evil\n".encode("utf-8"))
    assert any(f["category"] == "bidi" for f in findings)


def test_scan_bytes_skips_files_over_size_ceiling(tmp_path):
    p = tmp_path / "big.py"
    assert ws.scan_bytes(p, b"a" * (ws.MAX_FILE_SIZE + 1)) == []


def test_scan_bytes_skips_utf16_bom(tmp_path):
    p = tmp_path / "utf16.txt"
    assert ws.scan_bytes(p, b"\xff\xfe" + "hello".encode("utf-16-le")) == []


# --- Regression: content that must NEVER be flagged as a fixable watermark ---
# (apply_fix() operates on the working-tree file directly; no git required.)


def test_regression_emoji_zwj_sequence_not_fixed(tmp_path):
    """Family emoji ZWJ sequence — legitimate, must survive --fix untouched."""
    p = tmp_path / "bot_message.py"
    family = f"\U0001f468{ZWJ}\U0001f469{ZWJ}\U0001f467"
    original = f'msg = "{family}"\n'
    p.write_text(original, encoding="utf-8")
    findings = ws.scan_bytes(p, original.encode("utf-8"))
    fixed = ws.apply_fix(p, findings)
    assert fixed is False
    assert p.read_text(encoding="utf-8") == original


def test_regression_vs16_emoji_presentation_not_fixed(tmp_path):
    """VS16 emoji presentation selector — used 62x in shipping bot messages."""
    p = tmp_path / "bot_ui.py"
    info_emoji = f"ℹ{VS16}"  # INFORMATION SOURCE + VS16
    original = f'label = "{info_emoji} Info"\n'
    p.write_text(original, encoding="utf-8")
    findings = ws.scan_bytes(p, original.encode("utf-8"))
    fixed = ws.apply_fix(p, findings)
    assert fixed is False
    assert p.read_text(encoding="utf-8") == original


def test_regression_bom_csv_not_fixed(tmp_path):
    """BOM in a client CSV — --fix is restricted to .py/.js/.ts only."""
    p = tmp_path / "client_data.csv"
    original = f"{BOM}name,value\n"
    p.write_text(original, encoding="utf-8")
    findings = ws.scan_bytes(p, original.encode("utf-8"))
    fixed = ws.apply_fix(p, findings)
    assert fixed is False
    assert p.read_text(encoding="utf-8") == original


def test_regression_persian_zwnj_text_not_fixed(tmp_path):
    """Persian text using ZWNJ correctly (mi-ravam, 'I go') must not be touched."""
    p = tmp_path / "persian.py"
    greeting = f"می{ZWNJ}روم"  # mi + ZWNJ + ravam
    original = f'greeting = "{greeting}"\n'
    p.write_text(original, encoding="utf-8")
    findings = ws.scan_bytes(p, original.encode("utf-8"))
    fixed = ws.apply_fix(p, findings)
    assert fixed is False
    assert p.read_text(encoding="utf-8") == original


def test_regression_bidi_never_auto_fixed(tmp_path):
    """Bidi override is the attack signature itself — must never be silently repaired."""
    p = tmp_path / "trojan2.py"
    original = f"x = 1  # {RLO} evil\n"
    p.write_text(original, encoding="utf-8")
    findings = ws.scan_bytes(p, original.encode("utf-8"))
    fixed = ws.apply_fix(p, findings)
    assert fixed is False
    assert p.read_text(encoding="utf-8") == original


def test_fix_zwsp_in_py_file_is_atomic_and_undoable(tmp_path):
    p = tmp_path / "clean_me.py"
    original = f"x = 1{ZWSP}\n"
    p.write_text(original, encoding="utf-8")
    findings = ws.scan_bytes(p, original.encode("utf-8"))
    fixed = ws.apply_fix(p, findings)
    assert fixed is True
    assert ZWSP not in p.read_text(encoding="utf-8")
    assert not p.with_name(p.name + ".tmp").exists()


# --- Regression: real bypasses found under adversarial stress testing, now fixed ---


def test_regression_scan_reads_staged_index_not_working_tree(tmp_path, monkeypatch):
    """The scanner must catch content in the STAGED blob even if the working-tree
    copy was reverted to something clean without re-staging — this was a real,
    demonstrated bypass (stage malicious content, revert working tree, scanner
    reported clean, `git commit` still committed the malicious staged blob)."""
    repo = _git_repo(tmp_path)
    p = repo / "f.py"
    p.write_text(f"x = 1  # {RLO} evil\n", encoding="utf-8")
    _stage(repo, "f.py")
    # Revert working tree to clean content WITHOUT re-staging.
    p.write_text("x = 1  # clean\n", encoding="utf-8")
    monkeypatch.chdir(repo)
    findings = ws.scan_file(Path("f.py"))
    assert any(f["category"] == "bidi" for f in findings)


def test_regression_staged_symlink_is_skipped_not_followed(tmp_path, monkeypatch):
    """A staged symlink's real committed content is the target PATH STRING, not
    the target file's content. Following it (reading the target file's bytes)
    scans content that isn't what's actually being committed — skip instead."""
    repo = _git_repo(tmp_path)
    outside = tmp_path.parent / "outside_target.py"
    outside.write_text(f"token = 1  # {RLO} leaked\n", encoding="utf-8")
    link = repo / "link.py"
    link.symlink_to(outside)
    _stage(repo, "link.py")
    monkeypatch.chdir(repo)
    assert ws.staged_is_symlink(Path("link.py")) is True
    findings = ws.scan_file(Path("link.py"))
    assert findings == []


def test_regression_non_ascii_filename_is_still_scanned(tmp_path, monkeypatch):
    """git C-quotes non-ASCII filenames by default in `--name-only` output; without
    -z that quoted literal doesn't match a real path on disk and the file was
    silently skipped — a real bypass for accented/non-ASCII filenames."""
    repo = _git_repo(tmp_path)
    p = repo / "café.py"
    p.write_text(f"x = 1{ZWSP}\n", encoding="utf-8")
    _stage(repo, "café.py")
    monkeypatch.chdir(repo)
    files = ws.staged_files()
    assert any(f.name == "café.py" for f in files)
    findings = ws.scan_file(Path("café.py"))
    assert any(f["category"] == "zwsp" for f in findings)
