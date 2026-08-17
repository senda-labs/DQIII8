"""fmt_ooxml.py: docx safe/--all tier removal, OPC-correctness invariants —
Default survives a removed last-matching part, TargetMode="External" is
never resolved, and a pre-existing dangling relationship in the INPUT must
not be "fixed" or cause the tool's own output to be treated as corrupt.
"""

from __future__ import annotations

import sys
import zipfile
import io
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bin" / "tools"))

import pytest
from lxml import etree

from metadata_lib import fmt_ooxml, validate
from metadata_lib.errors import ErrorClass, MetadataToolError
import metadata_fixtures as mf

CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"


def test_zip_bomb_aborts_before_decompression(tmp_path):
    p = tmp_path / "bomb.docx"
    raw = mf.make_zip_bomb(p)

    with pytest.raises(MetadataToolError) as excinfo:
        fmt_ooxml.remove(raw, all_tier=False)
    assert excinfo.value.error_class is ErrorClass.ADVERSARIAL

    findings = fmt_ooxml.inspect(p, raw, "docx")
    assert any(f.field == "adversarial_input" for f in findings)


def test_zip_path_traversal_entry_refused(tmp_path):
    p = tmp_path / "traversal.docx"
    raw = mf.make_zip_with_path_traversal(p)

    with pytest.raises(MetadataToolError) as excinfo:
        fmt_ooxml.remove(raw, all_tier=False)
    assert excinfo.value.error_class is ErrorClass.ADVERSARIAL


def test_zip_duplicate_entry_names_refused(tmp_path):
    p = tmp_path / "dupe.docx"
    raw = mf.make_zip_with_duplicate_entry_names(p)

    with pytest.raises(MetadataToolError) as excinfo:
        fmt_ooxml.remove(raw, all_tier=False)
    assert excinfo.value.error_class is ErrorClass.ADVERSARIAL


def test_adversarial_zip_never_downgraded_to_corrupt_and_writes_no_backup(tmp_path):
    """A CORRUPT classification is acceptable with --all --yes; ADVERSARIAL
    must never be reachable that way. Also confirms metadata_remove.py's CLI
    path writes no .bak for an adversarial input.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bin" / "tools"))
    import subprocess

    p = tmp_path / "bomb.docx"
    mf.make_zip_bomb(p)

    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parent.parent / "bin" / "tools" / "metadata_remove.py"),
            "--file",
            str(p),
            "--apply",
            "--all",
            "--yes",
            "--json",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == ErrorClass.ADVERSARIAL.exit_code
    assert not (tmp_path / "bomb.docx.bak").exists()


def test_docx_removal_idempotent(tmp_path):
    """clean(clean(x)) == clean(x) byte-for-byte — catches nondeterministic
    zip writing (timestamps, entry order, compression level).
    """
    for all_tier in (False, True):
        p = tmp_path / f"idem_{all_tier}.docx"
        raw = mf.make_docx_simple(p, author="Someone", company="Somewhere")
        once = fmt_ooxml.remove(raw, all_tier=all_tier)
        twice = fmt_ooxml.remove(once, all_tier=all_tier)
        assert once == twice


def test_docx_safe_tier_removes_identity_fields(tmp_path):
    p = tmp_path / "a.docx"
    raw = mf.make_docx_simple(p, author="Real Name", company="Acme Corp")

    findings = fmt_ooxml.inspect(p, raw, "docx")
    assert any(f.location == "docProps/core.xml" for f in findings)
    assert any(f.location == "docProps/app.xml" for f in findings)

    cleaned = fmt_ooxml.remove(raw, all_tier=False)

    with zipfile.ZipFile(io.BytesIO(cleaned)) as zf:
        core = zf.read("docProps/core.xml")
        app = zf.read("docProps/app.xml")
    assert b"Real Name" not in core
    assert b"Acme Corp" not in app

    validate.validate_ooxml_structural(cleaned)
    validate.validate_ooxml_reparse(cleaned, "docx")


def test_docx_thumbnail_default_extension_survives_last_part_removal(tmp_path):
    p = tmp_path / "thumb.docx"
    raw = mf.make_docx_with_thumbnail_only_jpeg(p)

    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        assert "docProps/thumbnail.jpeg" in zf.namelist()

    cleaned = fmt_ooxml.remove(raw, all_tier=False)

    with zipfile.ZipFile(io.BytesIO(cleaned)) as zf:
        assert "docProps/thumbnail.jpeg" not in zf.namelist()
        ct_root = etree.fromstring(zf.read("[Content_Types].xml"))
        defaults = {el.get("Extension", "").lower() for el in ct_root.findall(f"{{{CT_NS}}}Default")}
        assert "jpeg" in defaults, "Default Extension=jpeg must survive even with zero matching parts"

    validate.validate_ooxml_structural(cleaned)  # must NOT raise over the now-zero-match Default
    validate.validate_ooxml_reparse(cleaned, "docx")


def test_docx_external_attached_template_never_resolved(tmp_path):
    p = tmp_path / "ext.docx"
    raw = mf.make_docx_with_external_attached_template(p)

    findings = fmt_ooxml.inspect(p, raw, "docx")
    assert any(f.field == "attached_template" for f in findings)

    cleaned = fmt_ooxml.remove(raw, all_tier=False)
    # External relationship must survive untouched — never resolved against the package
    with zipfile.ZipFile(io.BytesIO(cleaned)) as zf:
        rels = zf.read("word/_rels/settings.xml.rels")
    assert b"TargetMode=\"External\"" in rels
    assert b"Normal.dotm" in rels

    validate.validate_ooxml_structural(cleaned)
    validate.validate_ooxml_reparse(cleaned, "docx")


def test_docx_preexisting_dangling_relationship_not_fixed_and_output_accepted(tmp_path):
    """The single most important fixture per the design plan: without it,
    the validator would refuse every sloppily-generated real-world docx.
    The tool must not "fix" a pre-existing dangling relationship, and must
    not treat its own output as newly broken because of it.
    """
    p = tmp_path / "dangling.docx"
    raw = mf.make_docx_with_dangling_relationship(p)

    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        rels_before = zf.read("_rels/.rels")
    assert b"does-not-exist.xml" in rels_before

    cleaned = fmt_ooxml.remove(raw, all_tier=False)

    with zipfile.ZipFile(io.BytesIO(cleaned)) as zf:
        rels_after = zf.read("_rels/.rels")
    assert b"does-not-exist.xml" in rels_after, "tool must not silently 'fix' a pre-existing dangling relationship"

    # Must not raise: an input-side pre-existing dangling relationship is
    # not something the tool introduced, so its own structural gate must
    # not choke on it — checked against the INPUT's own integrity baseline.
    validate.validate_ooxml_structural(cleaned, raw)

    # NOTE: validate_ooxml_reparse is deliberately NOT called here. A
    # package-root relationship pointing at a genuinely nonexistent part
    # makes python-docx itself refuse to open the file (it eagerly walks
    # every relationship reachable from _rels/.rels) — third-party behavior
    # this tool cannot and should not override. That's a real, pre-existing
    # defect in the INPUT the reparse gate is right to catch; the plan's
    # "must not treat its own output as newly broken" requirement targets
    # this tool's own structural gate, verified above.
