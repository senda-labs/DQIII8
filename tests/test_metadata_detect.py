"""detect.py: magic-byte sniffing, extension-mismatch refusal, OOXML subtype
resolution from [Content_Types].xml (not extension), and detector totality.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bin" / "tools"))

from hypothesis import given, settings, strategies as st

from metadata_lib import detect
import metadata_fixtures as mf


def test_jpeg_detected_by_magic():
    p = Path("/tmp") / "unused.jpg"
    d = detect.detect(Path("x.jpg"), b"\xff\xd8\xff\xe0rest")
    assert d.format == "jpeg"
    assert d.mismatch is None


def test_extension_mismatch_refused_not_guessed(tmp_path):
    p = tmp_path / "invoice.pdf"
    mf.make_jpeg_plain(tmp_path / "real.jpg")
    raw = (tmp_path / "real.jpg").read_bytes()
    p.write_bytes(raw)
    d = detect.detect(p, raw)
    assert d.format == "jpeg"
    assert d.mismatch is not None


def test_matching_extension_no_mismatch(tmp_path):
    p = tmp_path / "photo.jpg"
    raw = mf.make_jpeg_plain(p)
    d = detect.detect(p, raw)
    assert d.mismatch is None


def test_ooxml_subtype_from_content_types_not_extension(tmp_path):
    """A .docx that legitimately declares a macro-enabled content type
    still resolves correctly — subtype comes from [Content_Types].xml.
    """
    p = tmp_path / "report.docx"
    raw = mf.make_docx_simple(p)
    d = detect.detect(p, raw)
    assert d.format == "ooxml"
    assert d.subtype == "docx"
    assert d.mismatch is None


def test_ooxml_extension_mismatch_detected(tmp_path):
    p = tmp_path / "report.xlsx"
    raw = mf.make_docx_simple(tmp_path / "real.docx")
    p.write_bytes(raw)
    d = detect.detect(p, raw)
    assert d.format == "ooxml"
    assert d.subtype == "docx"
    assert d.mismatch is not None


def test_unsupported_format_for_arbitrary_bytes():
    d = detect.detect(Path("x.bin"), b"not a known format at all")
    assert d.format == "unsupported"


def test_empty_bytes_does_not_raise():
    d = detect.detect(Path("x.bin"), b"")
    assert d.format == "unsupported"


@given(st.binary(min_size=0, max_size=64))
@settings(max_examples=200)
def test_detect_never_raises_on_arbitrary_bytes(data):
    d = detect.detect(Path("fuzz.bin"), data)
    assert d.format in ("jpeg", "png", "webp", "tiff", "pdf", "ooxml", "bmff", "unsupported")
