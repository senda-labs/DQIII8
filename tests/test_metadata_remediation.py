"""Regression tests for the adversarial-panel remediation pass (2026-08-14).

One test (or small cluster) per confirmed finding, reproducing the finding's
own documented failure scenario rather than a paraphrase of it. Fixtures are
built programmatically in tmp_path — zero committed binaries, per the standing
rule in tests/metadata_fixtures.py.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS = REPO_ROOT / "bin" / "tools"
sys.path.insert(0, str(TOOLS))

import metadata_fixtures as mf  # noqa: E402
from metadata_lib import fmt_image, fmt_pdf, safeio  # noqa: E402
from metadata_lib.errors import ErrorClass, worst  # noqa: E402


def _run(tool: str, args):
    return subprocess.run(
        [sys.executable, str(TOOLS / tool), *args], capture_output=True, text=True
    )


# ------------------------------------------------------------------ fix 1 ---
# Symlink-based arbitrary write via a pre-planted .bak / .tmp side file.


def test_safeio_bak_symlink_cannot_redirect_write(tmp_path):
    victim = tmp_path / "victim.txt"
    victim.write_bytes(b"VICTIM CONTENT")
    target = tmp_path / "a.bin"
    target.write_bytes(b"original")
    (tmp_path / "a.bin.bak").symlink_to(victim)

    result = safeio.atomic_replace(target, b"cleaned", backup_from=b"original")

    assert result.written is False
    assert victim.read_bytes() == b"VICTIM CONTENT"
    assert target.read_bytes() == b"original"


def test_safeio_dangling_bak_symlink_cannot_create_victim(tmp_path):
    victim = tmp_path / "does-not-exist-yet.txt"
    target = tmp_path / "a.bin"
    target.write_bytes(b"original")
    (tmp_path / "a.bin.bak").symlink_to(victim)

    result = safeio.atomic_replace(target, b"cleaned", backup_from=b"original")

    assert result.written is False
    assert not victim.exists()
    assert target.read_bytes() == b"original"


def test_safeio_tmp_symlink_cannot_redirect_write(tmp_path):
    victim = tmp_path / "victim.txt"
    victim.write_bytes(b"VICTIM CONTENT")
    target = tmp_path / "a.bin"
    target.write_bytes(b"original")
    (tmp_path / "a.bin.tmp").symlink_to(victim)

    result = safeio.atomic_replace(target, b"cleaned", backup_from=b"original")

    assert result.written is False
    assert victim.read_bytes() == b"VICTIM CONTENT"
    assert target.read_bytes() == b"original"
    assert not target.is_symlink()


def test_write_new_file_refuses_existing_symlink(tmp_path):
    victim = tmp_path / "victim.txt"
    victim.write_bytes(b"VICTIM")
    link = tmp_path / "link"
    link.symlink_to(victim)

    with pytest.raises(FileExistsError):
        safeio.write_new_file(link, b"attacker payload")
    assert victim.read_bytes() == b"VICTIM"


def test_metadata_remove_cli_refuses_planted_bak_symlink(tmp_path):
    victim = tmp_path / "victim.txt"
    victim.write_bytes(b"VICTIM CONTENT")
    img = tmp_path / "a.jpg"
    mf.make_jpeg_with_exif(img)
    before = img.read_bytes()
    (tmp_path / "a.jpg.bak").symlink_to(victim)

    result = _run("metadata_remove.py", ["--file", str(img), "--apply", "--json"])
    report = json.loads(result.stdout)

    assert report["results"][0]["status"] == "write_refused"
    assert victim.read_bytes() == b"VICTIM CONTENT"
    assert img.read_bytes() == before


def test_watermark_remove_refuses_planted_bak_symlink(tmp_path):
    victim = tmp_path / "victim.txt"
    victim.write_bytes(b"VICTIM CONTENT")
    f = tmp_path / "note.txt"
    f.write_text("hello" + chr(0x200B) + "world\n", encoding="utf-8")
    before = f.read_bytes()
    (tmp_path / "note.txt.bak").symlink_to(victim)

    result = _run("watermark_remove.py", ["--file", str(f), "--apply"])

    assert victim.read_bytes() == b"VICTIM CONTENT"
    assert f.read_bytes() == before
    assert "backup already exists" in result.stderr


def test_watermark_remove_refuses_planted_tmp_symlink(tmp_path):
    victim = tmp_path / "victim.txt"
    victim.write_bytes(b"VICTIM CONTENT")
    f = tmp_path / "note.txt"
    f.write_text("hello" + chr(0x200B) + "world\n", encoding="utf-8")
    before = f.read_bytes()
    (tmp_path / "note.txt.tmp").symlink_to(victim)

    _run("watermark_remove.py", ["--file", str(f), "--apply"])

    assert victim.read_bytes() == b"VICTIM CONTENT"
    assert f.read_bytes() == before
    assert not f.is_symlink()
    # a failed tmp write must not leave a half-done backup behind either
    assert not (tmp_path / "note.txt.bak").exists()


# ----------------------------------------------------------------- fix 13 ---


@pytest.mark.parametrize("big_endian", [False, True])
def test_watermark_remove_preserves_utf16_encoding(tmp_path, big_endian):
    f = tmp_path / "note.txt"
    raw = mf.make_utf16_text_with_zwsp(f, big_endian=big_endian)
    assert b"\x0b\x20" in raw or b"\x20\x0b" in raw  # ZWSP present in UTF-16

    result = _run("watermark_remove.py", ["--file", str(f), "--apply"])
    assert result.returncode == 0

    out = f.read_bytes()
    assert out[:2] == raw[:2], "byte-order mark (and thus the encoding) must survive"
    enc = "utf-16-be" if big_endian else "utf-16-le"
    assert out[2:].decode(enc) == "helloworld\n"


def test_watermark_remove_still_writes_utf8_as_utf8(tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("hello" + chr(0x200B) + "world\n", encoding="utf-8")
    _run("watermark_remove.py", ["--file", str(f), "--apply"])
    assert f.read_bytes() == b"helloworld\n"


# ------------------------------------------------------------------ fix 2 ---


def test_exiftool_check_and_execution_share_one_search_path():
    """The availability check must resolve against exactly the PATH the
    subprocess is given, so the two can never disagree.
    """
    import shutil

    assert fmt_image.resolve_exiftool() == shutil.which("exiftool", path=fmt_image.EXIFTOOL_PATH)


def test_exiftool_failure_is_not_a_silent_clean(tmp_path, monkeypatch):
    img = tmp_path / "a.jpg"
    raw = mf.make_jpeg_with_exif(img)

    def _boom(*_a, **_kw):
        raise OSError("exiftool exploded")

    monkeypatch.setattr(fmt_image, "exiftool_available", lambda: True)
    monkeypatch.setattr(fmt_image, "_list_tags_via_exiftool", _boom)

    findings = fmt_image.inspect(img, raw, "jpeg")
    assert [f.field for f in findings] == ["engine_error"]
    assert findings[0].removable is False
    assert findings[0].error_class is ErrorClass.ENGINE_FAILURE


def test_exiftool_engine_failure_aborts_removal_with_distinct_exit_code(tmp_path, monkeypatch):
    """With exiftool resolvable but every invocation failing, the run must end
    in the engine_failure status/exit code, never 0 ("nothing to remove"),
    and must leave the file byte-identical.
    """
    import metadata_remove

    img = tmp_path / "a.jpg"
    mf.make_jpeg_with_exif(img)
    before = img.read_bytes()

    def _fail(*_a, **_kw):
        raise subprocess.CalledProcessError(42, "exiftool")

    monkeypatch.setattr(fmt_image, "exiftool_available", lambda: True)
    monkeypatch.setattr(fmt_image, "_list_tags_via_exiftool", _fail)
    monkeypatch.setattr(fmt_image, "_run_exiftool_on_copy", _fail)

    r = metadata_remove.process_file(img, apply=True, all_tier=False, invocation_id="test")

    assert r["status"] == ErrorClass.ENGINE_FAILURE.label
    assert metadata_remove._exit_code_for([r]) == ErrorClass.ENGINE_FAILURE.exit_code
    assert img.read_bytes() == before
    assert not (tmp_path / "a.jpg.bak").exists()


def test_atomic_replace_oserror_is_a_clean_status_not_a_crash(tmp_path, monkeypatch):
    """2026-08-17 disaster testing: safeio.atomic_replace re-raises OSError
    (e.g. real ENOSPC, reproduced live against a 2MB tmpfs mount) after
    cleaning up its own .tmp. process_file() previously called it unguarded,
    so this exception propagated uncaught out of process_file and crashed the
    whole --dir batch on the first disk-full file — discarding every result
    already collected for files processed earlier in the sweep. It must
    instead come back as an ordinary per-file failure so the caller's loop
    continues, exactly like every other engine failure in this function.
    """
    import metadata_remove

    img = tmp_path / "a.jpg"
    mf.make_jpeg_with_exif(img)
    before = img.read_bytes()

    def _boom(*_a, **_kw):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(safeio, "atomic_replace", _boom)

    r = metadata_remove.process_file(img, apply=True, all_tier=False, invocation_id="test")

    assert r["status"] == "write_failed"
    assert "No space left on device" in r["note"]
    assert metadata_remove._exit_code_for([r]) == 1
    assert img.read_bytes() == before
    assert not (tmp_path / "a.jpg.bak").exists()
    assert not (tmp_path / "a.jpg.tmp").exists()


# ------------------------------------------------------------------ fix 3 ---


@pytest.mark.skipif(fmt_image.resolve_exiftool() is None, reason="exiftool not installed")
def test_xmp_namespace_groups_are_detected(tmp_path):
    img = tmp_path / "a.jpg"
    raw = mf.make_jpeg_with_xmp(img)

    findings = fmt_image.inspect(img, raw, "jpeg")
    locations = [f.location for f in findings if f.field == "identity_metadata"]

    assert any(loc.startswith("XMP-") or loc == "XMP" for loc in locations), (
        f"XMP was never flagged; groups seen: {[f.location for f in findings]}"
    )


def test_is_identity_group_matches_namespaced_xmp():
    assert fmt_image._is_identity_group("XMP-dc")
    assert fmt_image._is_identity_group("XMP-photoshop")
    assert fmt_image._is_identity_group("XMP")
    assert not fmt_image._is_identity_group("File")
    assert not fmt_image._is_identity_group("PNG")


# ------------------------------------------------------------------ fix 4 ---


def _open_out(raw: bytes):
    import pikepdf

    return pikepdf.open(io.BytesIO(raw))


def test_safe_tier_preserves_non_c2pa_embedded_attachment(tmp_path):
    p = tmp_path / "invoice.pdf"
    raw = mf.make_pdf_with_embedded_attachment(p)

    out = fmt_pdf.remove(raw, all_tier=False)
    with _open_out(out) as pdf:
        af = list(pdf.Root.get("/AF", []))
        assert len(af) == 1
        assert bytes(af[0]["/EF"]["/F"].read_bytes()) == b"<Invoice>real content</Invoice>"
        tree = pdf.Root.Names.EmbeddedFiles
        names = list(tree["/Names"])
        assert str(names[0]) == "factur-x.xml"


def test_safe_tier_prunes_only_the_c2pa_manifest_entry(tmp_path):
    p = tmp_path / "both.pdf"
    raw = mf.make_pdf_with_c2pa_and_attachment(p)

    out = fmt_pdf.remove(raw, all_tier=False)
    with _open_out(out) as pdf:
        af = list(pdf.Root.get("/AF", []))
        assert [str(e.get("/F")) for e in af] == ["factur-x.xml"]
        assert bytes(af[0]["/EF"]["/F"].read_bytes()) == b"<Invoice>real content</Invoice>"

        tree = pdf.Root.Names.EmbeddedFiles
        names = list(tree["/Names"])
        assert [str(n) for n in names[::2]] == ["factur-x.xml"]
        assert len(names) % 2 == 0, "/Names must stay a flat [key, value, ...] array"


def test_non_manifest_attachment_is_reported_as_non_removable(tmp_path):
    p = tmp_path / "invoice.pdf"
    raw = mf.make_pdf_with_embedded_attachment(p)

    findings = fmt_pdf.inspect(p, raw)
    attach = [f for f in findings if f.field == "embedded_file_attachment"]
    assert len(attach) == 1
    assert attach[0].removable is False, (
        "a removable safe-tier finding would just reintroduce the destruction one layer down"
    )
    assert attach[0].tier == "safe"


def test_attachment_shows_up_in_left_in_place_audit_entry(tmp_path, monkeypatch):
    import metadata_remove

    p = tmp_path / "invoice.pdf"
    mf.make_pdf_with_embedded_attachment(p)

    records = []
    monkeypatch.setattr(metadata_remove.audit_log, "append", lambda rec: records.append(rec))
    r = metadata_remove.process_file(p, apply=True, all_tier=False, invocation_id="test")

    assert r["status"] == "written"
    assert any(e["field"] == "embedded_file_attachment" for e in records[0]["left_in_place"])


# ------------------------------------------------------------------ fix 5 ---


def test_encrypted_pdf_is_not_reported_as_success(tmp_path):
    p = tmp_path / "enc.pdf"
    mf.make_pdf_encrypted(p)
    before = p.read_bytes()

    result = _run("metadata_remove.py", ["--file", str(p), "--apply", "--json"])
    report = json.loads(result.stdout)

    assert report["results"][0]["status"] == ErrorClass.ENCRYPTED_OR_SIGNED.label
    assert result.returncode == ErrorClass.ENCRYPTED_OR_SIGNED.exit_code
    assert p.read_bytes() == before


def test_corrupt_pdf_is_not_reported_as_success(tmp_path):
    p = tmp_path / "broken.pdf"
    p.write_bytes(b"%PDF-1.4\nnot really a pdf at all\n")
    before = p.read_bytes()

    result = _run("metadata_remove.py", ["--file", str(p), "--apply", "--json"])
    report = json.loads(result.stdout)

    assert report["results"][0]["status"] != "no_target_tier_findings"
    assert result.returncode != 0
    assert p.read_bytes() == before


def test_engine_error_class_is_structured_not_reparsed_from_note(tmp_path):
    """A message that itself contains a colon must not shift the resolved
    ErrorClass — the whole reason the enum is carried as a field.
    """
    p = tmp_path / "enc.pdf"
    mf.make_pdf_encrypted(p)

    findings = fmt_pdf.inspect(p, p.read_bytes())
    assert findings[0].field == "engine_error"
    assert findings[0].error_class is ErrorClass.ENCRYPTED_OR_SIGNED
    assert findings[0].to_dict()["error_class"] == "encrypted_or_signed"


# ---------------------------------------------------------------- fix 6/7 ---


def test_worst_never_lets_engine_failure_mask_adversarial():
    assert worst([ErrorClass.ENGINE_FAILURE, ErrorClass.ADVERSARIAL]) is ErrorClass.ADVERSARIAL
    assert worst([ErrorClass.ADVERSARIAL, ErrorClass.ENGINE_FAILURE]) is ErrorClass.ADVERSARIAL
    assert worst([ErrorClass.CORRUPT, ErrorClass.ENGINE_FAILURE]) is ErrorClass.ENGINE_FAILURE
    assert worst([]) is None


def test_benign_unsupported_does_not_mask_an_unlabelled_error():
    """A single UNSUPPORTED (exit 0 by design) used to make the resolver
    return early, hiding every status with no ErrorClass label in the batch.
    """
    import metadata_remove

    results = [
        {"status": ErrorClass.UNSUPPORTED.label},
        {"status": "unreadable"},
    ]
    assert metadata_remove._exit_code_for(results) == 1


def test_unlabelled_statuses_each_produce_a_nonzero_exit():
    import metadata_remove

    for status in ("unreadable", "symlink_refused", "write_refused", "no_change"):
        assert metadata_remove._exit_code_for([{"status": status}]) != 0, status


def test_adversarial_outranks_engine_failure_in_mixed_batch():
    import metadata_remove

    results = [
        {"status": ErrorClass.ENGINE_FAILURE.label},
        {"status": ErrorClass.ADVERSARIAL.label},
    ]
    assert metadata_remove._exit_code_for(results) == ErrorClass.ADVERSARIAL.exit_code


def test_all_success_statuses_exit_zero():
    import metadata_remove

    results = [{"status": s} for s in metadata_remove.SUCCESS_STATUSES]
    assert metadata_remove._exit_code_for(results) == 0


def test_mixed_batch_real_cli(tmp_path):
    """End-to-end version of the masking bug: an unsupported file (exit 0 by
    design) alongside an encrypted PDF must still surface the real error.
    """
    (tmp_path / "note.txt").write_bytes(b"just text, unsupported format")
    mf.make_pdf_encrypted(tmp_path / "enc.pdf")

    result = _run("metadata_remove.py", ["--dir", str(tmp_path), "--apply", "--json"])
    assert result.returncode == ErrorClass.ENCRYPTED_OR_SIGNED.exit_code


# ------------------------------------------------------------------ fix 8 ---


def test_tiff_findings_are_not_advertised_as_removable(tmp_path):
    p = tmp_path / "a.tiff"
    raw = mf.make_tiff_with_exif(p)

    findings = fmt_image.inspect(p, raw, "tiff")
    assert findings, "fixture should carry detectable TIFF metadata"
    assert all(f.removable is False for f in findings), (
        "metadata_remove._transform has no TIFF branch — promising removal is a false claim"
    )


def test_tiff_apply_does_not_claim_a_write(tmp_path):
    p = tmp_path / "a.tiff"
    mf.make_tiff_with_exif(p)
    before = p.read_bytes()

    result = _run("metadata_remove.py", ["--file", str(p), "--apply", "--json"])
    report = json.loads(result.stdout)

    assert report["results"][0]["status"] != "written"
    assert p.read_bytes() == before
