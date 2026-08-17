"""Regression tests for the 2026-08-16 metadata/watermark re-audit.

Each test asserts the *bug*, so it fails against the pre-fix code. Several are
deliberately negative — they pin the direction in which a fix could break
something, which is where the adversarial review of the fix plan found a P0
(a bare "-Comment=" in the shared exiftool arg list would have destroyed
PNG tEXt chunks during a safe-tier --apply).
"""

from __future__ import annotations

import importlib.util
import io
import json
import struct
import sys
import zipfile
import zlib
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent / "bin" / "tools"
sys.path.insert(0, str(TOOLS))

from metadata_lib import audit_log, fmt_image, fmt_ooxml  # noqa: E402
from metadata_lib.report import Summary, build_report  # noqa: E402


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


metadata_audit = _load("metadata_audit")
metadata_purge_backups = _load("metadata_purge_backups")
watermark_audit = _load("watermark_audit")
watermark_remove = _load("watermark_remove")


# --------------------------------------------------------------------------
# F1 — OOXML removable must be gated on subtype (remove() implements docx only)
# --------------------------------------------------------------------------


def _minimal_ooxml(tmp_path: Path, name: str, ctype: str) -> Path:
    p = tmp_path / name
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("[Content_Types].xml", f'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/x" ContentType="{ctype}"/></Types>')
        z.writestr(
            "docProps/core.xml",
            '<?xml version="1.0"?><cp:coreProperties '
            'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/">'
            "<dc:creator>Iker Martins</dc:creator></cp:coreProperties>",
        )
    return p


@pytest.mark.parametrize("subtype", ["xlsx", "pptx"])
def test_ooxml_findings_not_removable_for_unimplemented_subtypes(tmp_path, subtype):
    p = _minimal_ooxml(tmp_path, f"f.{subtype}", "application/x")
    findings = fmt_ooxml.inspect(p, p.read_bytes(), subtype)
    assert findings, "expected at least the core.xml identity finding"
    assert all(not f.removable for f in findings), (
        f"{subtype} findings must not claim removable=True — metadata_remove._transform "
        f"raises UNSUPPORTED for {subtype}, so --apply can never honour the promise"
    )
    assert any("removal not implemented" in (f.note or "") for f in findings)


def test_ooxml_docx_findings_stay_removable(tmp_path):
    """Negative: the subtype gate must not disable the one path that works."""
    p = _minimal_ooxml(tmp_path, "f.docx", "application/x")
    findings = fmt_ooxml.inspect(p, p.read_bytes(), "docx")
    assert any(f.removable for f in findings), "docx removal must remain advertised"


# --------------------------------------------------------------------------
# F2 — a truncated sweep must never read as a complete clean sweep
# --------------------------------------------------------------------------


def test_metadata_audit_truncation_reaches_json_and_exit_code(tmp_path, capsys):
    for i in range(3):
        (tmp_path / f"f{i}.txt").write_text("plain\n")
    findings, skips, scanned, truncated = metadata_audit.scan_directory(tmp_path, 1, 10**9)
    assert truncated, "cap must be reported out of scan_directory, not just to stderr"

    rc = metadata_audit.report(findings, skips, scanned, str(tmp_path), True, truncated)
    body = json.loads(capsys.readouterr().out)
    assert body["truncated"] == truncated
    assert rc == metadata_audit.EXIT_TRUNCATED


def test_metadata_audit_exit_precedence_truncated_outranks_degraded():
    """Truncated AND degraded must be deterministic, not undefined."""
    assert metadata_audit._exit_code([], ["exiftool absent"], "cap hit") == metadata_audit.EXIT_TRUNCATED
    assert metadata_audit._exit_code([], ["exiftool absent"], None) == 2
    assert metadata_audit._exit_code(["f"], [], None) == 1
    assert metadata_audit._exit_code([], [], None) == 0


def test_watermark_audit_truncated_clean_sweep_is_not_exit_zero(tmp_path, monkeypatch):
    for i in range(3):
        (tmp_path / f"f{i}.txt").write_text("nothing hidden\n")
    monkeypatch.setattr(watermark_audit, "MAX_DIR_FILES", 1)
    findings, skips, truncated = watermark_audit.scan_directory(tmp_path)
    assert truncated
    assert watermark_audit.report(findings, skips, truncated) == watermark_audit.EXIT_TRUNCATED


def test_watermark_remove_reports_truncation(tmp_path, monkeypatch):
    for i in range(3):
        (tmp_path / f"f{i}.txt").write_text("nothing hidden\n")
    monkeypatch.setattr(watermark_remove, "MAX_DIR_FILES", 1)
    _files, _skips, truncated = watermark_remove.collect_files(tmp_path, None)
    assert truncated


# --------------------------------------------------------------------------
# F3 — unknown skip reasons must not be dropped from the report
# --------------------------------------------------------------------------


def test_unknown_skip_reasons_survive_into_the_report(capsys):
    metadata_audit.report([], {"unreadable": 3, "corrupt": 1}, 0, "/x", True)
    skipped = json.loads(capsys.readouterr().out)["summary"]["skipped"]
    assert skipped["unreadable"] == 3, "an unexamined file must not vanish from the report"
    assert skipped["corrupt"] == 1


def test_build_report_truncated_is_additive():
    body = build_report("t", "1", "now", "/r", Summary(), {}, [], [])
    assert body["truncated"] is None
    assert {"schema_version", "summary", "engines", "degraded", "findings"} <= set(body)


# --------------------------------------------------------------------------
# F4 — purge path matching
# --------------------------------------------------------------------------


def test_purge_matches_absolute_entry_regardless_of_cwd(tmp_path):
    """The logged path and the discovered path denote the same file but are not
    string-equal — raw equality (the pre-fix behaviour) misses it and the backup
    is never purged."""
    sub = tmp_path / "sub"
    (sub / "nested").mkdir(parents=True)
    target = sub / "shot.jpg"
    target.write_bytes(b"x")
    logged = str(tmp_path / "sub" / "nested" / ".." / "shot.jpg")
    assert logged != str(target)
    assert metadata_purge_backups._path_matches(logged, target)


def test_purge_legacy_relative_entry_does_not_bind_to_purge_cwd():
    """Negative: resolving a legacy relative entry against the purge run's cwd
    could match a same-named file that the entry never described."""
    assert not metadata_purge_backups._path_matches("shot.jpg", Path("/somewhere/else/shot.jpg"))
    assert metadata_purge_backups._path_matches("shot.jpg", Path("shot.jpg"))


# --------------------------------------------------------------------------
# F5 — JPEG COM segment, and the PNG tier invariant it must not break
# --------------------------------------------------------------------------


def _jpeg_with_com(payload: bytes = b"AUTHOR SECRET NOTE") -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (10, 20, 30)).save(buf, format="JPEG")
    raw = buf.getvalue()
    seg = b"\xff\xfe" + struct.pack(">H", len(payload) + 2) + payload
    return raw[:2] + seg + raw[2:]


def test_jpeg_comment_is_detected_and_removed_by_fallback():
    raw = _jpeg_with_com()
    findings = fmt_image._inspect_fallback(Path("x.jpg"), raw, "jpeg")
    assert any(f.field == "jpeg_comment" for f in findings), "COM segment must not read as clean"

    out = fmt_image._remove_fallback(raw, "jpeg", all_tier=False)
    assert b"AUTHOR SECRET NOTE" not in out
    from PIL import Image

    Image.open(io.BytesIO(out)).load()  # must still decode


def test_png_text_chunk_is_not_touched_by_safe_tier_removal():
    """Negative / P0 guard: a PNG `Comment` tEXt chunk is an --all-tier finding.
    A safe-tier removal must leave it byte-identical — the shared exiftool arg
    list must never carry an unconditional -Comment=.
    """
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (1, 2, 3)).save(buf, format="PNG")
    raw = buf.getvalue()
    ihdr_len = struct.unpack(">I", raw[8:12])[0]
    end = 8 + 8 + ihdr_len + 4
    payload = b"Comment\x00PNG SECRET COMMENT"
    chunk = struct.pack(">I", len(payload)) + b"tEXt" + payload + struct.pack(">I", zlib.crc32(b"tEXt" + payload) & 0xFFFFFFFF)
    raw = raw[:end] + chunk + raw[end:]

    findings = fmt_image._inspect_fallback(Path("x.png"), raw, "png")
    text = [f for f in findings if f.field == "text_chunk"]
    assert text and all(f.tier == "all" for f in text), "PNG text chunk must stay --all tier"

    out = fmt_image.remove(raw, "png", all_tier=False)
    assert b"PNG SECRET COMMENT" in out, "safe tier must not delete an --all-tier PNG chunk"


def test_safe_clear_args_has_no_unconditional_comment():
    assert "-Comment=" not in fmt_image._SAFE_CLEAR_ARGS, (
        "the arg list is shared by jpeg/png/webp — -Comment= must be added per-format"
    )


# --------------------------------------------------------------------------
# F6 — watermark_remove must distinguish "eligible" from "written"
# --------------------------------------------------------------------------


def test_watermark_remove_refusal_is_signalled(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("x" + chr(0x200B) + "y\n")
    (tmp_path / "a.txt.tmp").symlink_to(tmp_path / "nonexistent-victim")

    findings, written, refused = watermark_remove.remove_from_file(p, True, False)
    assert findings and not written and refused, "a blocked write must not look like a no-op"


def test_watermark_remove_benign_not_written_is_not_a_refusal(tmp_path):
    """Negative: dry runs and out-of-tier findings must not report a refusal,
    or a perfectly normal run would start exiting non-zero."""
    p = tmp_path / "a.txt"
    p.write_text("x" + chr(0x200B) + "y\n")
    _f, written, refused = watermark_remove.remove_from_file(p, False, False)  # dry run
    assert not written and not refused

    clean = tmp_path / "clean.txt"
    clean.write_text("nothing\n")
    _f, written, refused = watermark_remove.remove_from_file(clean, True, False)
    assert not written and not refused


def test_watermark_remove_unreadable_file_is_not_silent(tmp_path, capsys):
    missing = tmp_path / "gone.txt"
    findings, written, refused = watermark_remove.remove_from_file(missing, True, False)
    assert not findings and not written
    assert refused, "an unreadable file must not be an invisible skip in a privacy tool"


# --------------------------------------------------------------------------
# F9 — audit log must refuse a symlinked path and never block a clean
# --------------------------------------------------------------------------


def test_audit_log_refuses_symlinked_path_without_raising(tmp_path, capsys):
    victim = tmp_path / "victim.txt"
    victim.write_text("ORIGINAL\n")
    link = tmp_path / "log.jsonl"
    link.symlink_to(victim)

    audit_log.append({"x": 1}, log_path=link)  # must not raise

    assert victim.read_text() == "ORIGINAL\n", "log append must not follow a symlink into a victim file"
    assert "WARNING" in capsys.readouterr().err


def test_audit_log_normal_append_still_works(tmp_path):
    log = tmp_path / "log.jsonl"
    audit_log.append({"x": 1}, log_path=log)
    audit_log.append({"x": 2}, log_path=log)
    lines = [json.loads(line) for line in log.read_text().splitlines()]
    assert [r["x"] for r in lines] == [1, 2]
    assert log.stat().st_mode & 0o777 == 0o600
