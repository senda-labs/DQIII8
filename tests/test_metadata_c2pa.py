"""fmt_c2pa.py: JUMBF(JPEG)/caBX(PNG) detection+removal, including a JUMBF
box split across multiple APP11 continuation segments — a run that leaves
segment 2 behind must fail this test.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bin" / "tools"))

from metadata_lib import fmt_c2pa, validate
import metadata_fixtures as mf


def test_jpeg_c2pa_single_segment_detected_and_removed(tmp_path):
    p = tmp_path / "c2pa.jpg"
    raw = mf.make_jpeg_with_c2pa_app11(p, split_segments=False)
    findings = fmt_c2pa.detect_jpeg_c2pa(str(p), raw)
    assert len(findings) == 1
    assert findings[0].removable and findings[0].tier == "safe"

    cleaned = fmt_c2pa.remove_jpeg_c2pa(raw)
    assert mf.JUMBF_TYPE_UUID not in cleaned
    assert fmt_c2pa.detect_jpeg_c2pa(str(p), cleaned) == []
    validate.validate_image_structural(raw, cleaned)


def test_jpeg_c2pa_split_segments_fully_removed(tmp_path):
    p = tmp_path / "c2pa_split.jpg"
    raw = mf.make_jpeg_with_c2pa_app11(p, split_segments=True)

    findings = fmt_c2pa.detect_jpeg_c2pa(str(p), raw)
    assert len(findings) == 1  # grouped as one physically-contiguous span, not two findings

    cleaned = fmt_c2pa.remove_jpeg_c2pa(raw)
    assert mf.JUMBF_TYPE_UUID not in cleaned
    assert cleaned.count(b"\xff\xeb") == 0  # no leftover APP11 continuation segment
    validate.validate_image_structural(raw, cleaned)


def test_png_cabx_detected_and_removed(tmp_path):
    p = tmp_path / "c2pa.png"
    raw = mf.make_png_with_cabx(p)

    findings = fmt_c2pa.detect_png_c2pa(str(p), raw)
    assert len(findings) == 1

    cleaned = fmt_c2pa.remove_png_c2pa(raw)
    assert b"caBX" not in cleaned
    assert fmt_c2pa.detect_png_c2pa(str(p), cleaned) == []
    validate.validate_image_structural(raw, cleaned)


def test_jpeg_without_c2pa_no_false_positive(tmp_path):
    p = tmp_path / "plain.jpg"
    raw = mf.make_jpeg_plain(p)
    assert fmt_c2pa.detect_jpeg_c2pa(str(p), raw) == []
