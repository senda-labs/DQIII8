"""fmt_pdf.py: /Info detection+removal, encrypted-PDF refusal, and the core
claim over exiftool -all=: a full-rewrite save drops incremental-update
history, so a revision-1-only author string is byte-absent from output.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bin" / "tools"))

import pytest

from metadata_lib import fmt_pdf, validate
from metadata_lib.errors import ErrorClass, MetadataToolError
import metadata_fixtures as mf


def test_pdf_info_author_detected(tmp_path):
    p = tmp_path / "a.pdf"
    raw = mf.make_pdf_simple(p, author="Alice Example")
    findings = fmt_pdf.inspect(p, raw)
    assert any(f.location == "/Info" and f.tier == "safe" and f.removable for f in findings)


def test_pdf_safe_tier_removes_info_and_preserves_page_count(tmp_path):
    p = tmp_path / "a.pdf"
    raw = mf.make_pdf_simple(p, author="Alice Example")
    cleaned = fmt_pdf.remove(raw, all_tier=False)

    after = fmt_pdf.inspect(p, cleaned)
    assert not any(f.location == "/Info" for f in after)

    validate.validate_pdf(raw, cleaned, allow_recovered=True)  # raises on any regression


def test_pdf_incremental_history_dropped_by_full_rewrite(tmp_path):
    p = tmp_path / "g.pdf"
    raw = mf.make_pdf_incremental_two_revisions(p, rev1_author="REV1SECRET", rev2_author="REV2CURRENT")
    assert b"REV1SECRET" in raw  # sanity: fixture really carries both revisions

    cleaned = fmt_pdf.remove(raw, all_tier=False)

    assert b"REV1SECRET" not in cleaned
    assert b"REV2CURRENT" not in cleaned  # current author is also an /Info field, also safe-tier
    validate.validate_pdf(raw, cleaned, allow_recovered=True)


def test_pdf_encrypted_refused_on_inspect(tmp_path):
    p = tmp_path / "enc.pdf"
    raw = mf.make_pdf_encrypted(p)
    findings = fmt_pdf.inspect(p, raw)
    assert any(f.field == "engine_error" and "encrypted" in f.note for f in findings)


def test_pdf_encrypted_refused_on_remove(tmp_path):
    p = tmp_path / "enc.pdf"
    raw = mf.make_pdf_encrypted(p)
    with pytest.raises(MetadataToolError) as exc:
        fmt_pdf.remove(raw, all_tier=False)
    assert exc.value.error_class == ErrorClass.ENCRYPTED_OR_SIGNED


def test_pdf_signed_detected_and_refused_at_safe_tier(tmp_path):
    p = tmp_path / "signed.pdf"
    raw = mf.make_pdf_signed(p, author="Signer Author")

    findings = fmt_pdf.inspect(p, raw)
    assert any(f.field == "digital_signature" and f.tier == "all" for f in findings)

    with pytest.raises(MetadataToolError) as exc:
        fmt_pdf.remove(raw, all_tier=False)
    assert exc.value.error_class == ErrorClass.ENCRYPTED_OR_SIGNED


def test_pdf_signed_removed_with_all_tier(tmp_path):
    p = tmp_path / "signed.pdf"
    raw = mf.make_pdf_signed(p, author="Signer Author")

    cleaned = fmt_pdf.remove(raw, all_tier=True)

    after = fmt_pdf.inspect(p, cleaned)
    assert not any(f.location == "/Info" for f in after)
    validate.validate_pdf(raw, cleaned, allow_recovered=True)
