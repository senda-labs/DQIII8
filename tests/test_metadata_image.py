"""fmt_image.py: EXIF/IPTC/XMP detection+removal for JPEG/PNG, safe-tier
pixel-identity invariant, ICC-profile survival at the safe tier.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bin" / "tools"))

from hypothesis import HealthCheck, given, settings, strategies as st

from metadata_lib import fmt_image, validate
import metadata_fixtures as mf


def test_jpeg_exif_detected_at_safe_tier(tmp_path):
    p = tmp_path / "a.jpg"
    raw = mf.make_jpeg_with_exif(p)
    findings = fmt_image.inspect(p, raw, "jpeg")
    assert any(f.tier == "safe" and f.removable for f in findings)


def test_jpeg_exif_removal_clears_findings_and_preserves_pixels(tmp_path):
    p = tmp_path / "a.jpg"
    raw = mf.make_jpeg_with_exif(p)
    cleaned = fmt_image.remove(raw, "jpeg", all_tier=False)

    after = fmt_image.inspect(p, cleaned, "jpeg")
    assert not any(f.tier == "safe" and f.removable for f in after)

    validate.validate_image_structural(raw, cleaned)  # raises on any mismatch


def test_jpeg_plain_no_findings(tmp_path):
    p = tmp_path / "b.jpg"
    raw = mf.make_jpeg_plain(p)
    findings = fmt_image.inspect(p, raw, "jpeg")
    assert findings == []


def test_png_text_chunk_reported_all_tier_and_survives_safe_removal(tmp_path):
    """Per the plan's tier table, PNG text chunks are content-adjacent
    (--all tier), not safe tier — safe-tier removal must leave them.
    """
    p = tmp_path / "d.png"
    raw = mf.make_png_with_text_chunk(p)
    findings = fmt_image.inspect(p, raw, "png")
    assert any(f.removable and f.tier == "all" and f.field == "text_chunk" for f in findings)

    cleaned = fmt_image.remove(raw, "png", all_tier=False)
    after = fmt_image.inspect(p, cleaned, "png")
    assert any(f.tier == "all" and f.field == "text_chunk" for f in after)
    validate.validate_image_structural(raw, cleaned)


def test_png_text_chunk_removed_at_all_tier(tmp_path):
    p = tmp_path / "d.png"
    raw = mf.make_png_with_text_chunk(p)
    cleaned = fmt_image.remove(raw, "png", all_tier=True)
    after = fmt_image.inspect(p, cleaned, "png")
    assert not any(f.field == "text_chunk" for f in after)
    validate.validate_image_structural(raw, cleaned)


@given(
    w=st.integers(min_value=4, max_value=40),
    h=st.integers(min_value=4, max_value=40),
    author=st.text(min_size=1, max_size=20, alphabet=st.characters(blacklist_categories=("Cs",), max_codepoint=0x2000)),
)
@settings(max_examples=15, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_image_roundtrip_pixel_invariant(tmp_path, w, h, author):
    """Property: safe-tier removal on a random-size JPEG with a random EXIF
    Artist value always yields unchanged decoded-pixel sha256.
    """
    from PIL import Image
    import hashlib

    p = tmp_path / f"prop_{w}x{h}.jpg"
    img = Image.new("RGB", (w, h), color=(w % 255, h % 255, 7))
    exif = Image.Exif()
    try:
        exif[0x013B] = author
    except Exception:  # noqa: BLE001 - some codepoints aren't encodable by PIL's exif writer
        return  # not the invariant under test
    img.save(p, format="JPEG", exif=exif)
    raw = p.read_bytes()

    cleaned = fmt_image.remove(raw, "jpeg", all_tier=False)

    orig_pixels = hashlib.sha256(Image.open(p).convert("RGB").tobytes()).hexdigest()
    import io as _io

    new_pixels = hashlib.sha256(Image.open(_io.BytesIO(cleaned)).convert("RGB").tobytes()).hexdigest()
    assert orig_pixels == new_pixels
