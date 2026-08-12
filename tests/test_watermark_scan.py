"""Tests for bin/tools/watermark_scan.py.

Covers one positive case per detectable category, plus explicit regression
cases for content that must never be flagged for auto-fix or mangled.

All fixture strings use \\uXXXX escapes rather than raw literal codepoints,
so this source file itself never contains the invisible/hidden characters
under test (the pre-commit watermark-scan hook would otherwise correctly
flag its own test fixtures as findings).
"""

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


def test_scan_file_finds_zwsp(tmp_path):
    p = tmp_path / "watermarked.py"
    p.write_text(f"x = 1{ZWSP}\n", encoding="utf-8")
    findings = ws.scan_file(p)
    assert any(f["category"] == "zwsp" for f in findings)


def test_scan_file_finds_bidi_override(tmp_path):
    p = tmp_path / "trojan.py"
    p.write_text(f"x = 1  # {RLO} evil\n", encoding="utf-8")
    findings = ws.scan_file(p)
    assert any(f["category"] == "bidi" for f in findings)


def test_scan_file_skips_files_over_size_ceiling(tmp_path):
    p = tmp_path / "big.py"
    p.write_bytes(b"a" * (ws.MAX_FILE_SIZE + 1))
    assert ws.scan_file(p) == []


def test_scan_file_skips_utf16_bom(tmp_path):
    p = tmp_path / "utf16.txt"
    p.write_bytes(b"\xff\xfe" + "hello".encode("utf-16-le"))
    assert ws.scan_file(p) == []


# --- Regression: content that must NEVER be flagged as a fixable watermark ---


def test_regression_emoji_zwj_sequence_not_fixed(tmp_path):
    """Family emoji ZWJ sequence — legitimate, must survive --fix untouched."""
    p = tmp_path / "bot_message.py"
    family = f"\U0001F468{ZWJ}\U0001F469{ZWJ}\U0001F467"
    original = f'msg = "{family}"\n'
    p.write_text(original, encoding="utf-8")
    findings = ws.scan_file(p)
    fixed = ws.apply_fix(p, findings)
    assert fixed is False
    assert p.read_text(encoding="utf-8") == original


def test_regression_vs16_emoji_presentation_not_fixed(tmp_path):
    """VS16 emoji presentation selector — used 62x in shipping bot messages."""
    p = tmp_path / "bot_ui.py"
    info_emoji = f"ℹ{VS16}"  # INFORMATION SOURCE + VS16
    original = f'label = "{info_emoji} Info"\n'
    p.write_text(original, encoding="utf-8")
    findings = ws.scan_file(p)
    fixed = ws.apply_fix(p, findings)
    assert fixed is False
    assert p.read_text(encoding="utf-8") == original


def test_regression_bom_csv_not_fixed(tmp_path):
    """BOM in a client CSV — --fix is restricted to .py/.js/.ts only."""
    p = tmp_path / "client_data.csv"
    original = f"{BOM}name,value\n"
    p.write_text(original, encoding="utf-8")
    findings = ws.scan_file(p)
    fixed = ws.apply_fix(p, findings)
    assert fixed is False
    assert p.read_text(encoding="utf-8") == original


def test_regression_persian_zwnj_text_not_fixed(tmp_path):
    """Persian text using ZWNJ correctly (mi-ravam, 'I go') must not be touched."""
    p = tmp_path / "persian.py"
    greeting = f"می{ZWNJ}روم"  # mi + ZWNJ + ravam
    original = f'greeting = "{greeting}"\n'
    p.write_text(original, encoding="utf-8")
    findings = ws.scan_file(p)
    fixed = ws.apply_fix(p, findings)
    assert fixed is False
    assert p.read_text(encoding="utf-8") == original


def test_regression_bidi_never_auto_fixed(tmp_path):
    """Bidi override is the attack signature itself — must never be silently repaired."""
    p = tmp_path / "trojan2.py"
    original = f"x = 1  # {RLO} evil\n"
    p.write_text(original, encoding="utf-8")
    findings = ws.scan_file(p)
    fixed = ws.apply_fix(p, findings)
    assert fixed is False
    assert p.read_text(encoding="utf-8") == original


def test_fix_zwsp_in_py_file_is_atomic_and_undoable(tmp_path):
    p = tmp_path / "clean_me.py"
    p.write_text(f"x = 1{ZWSP}\n", encoding="utf-8")
    findings = ws.scan_file(p)
    fixed = ws.apply_fix(p, findings)
    assert fixed is True
    assert ZWSP not in p.read_text(encoding="utf-8")
    assert not p.with_name(p.name + ".tmp").exists()
