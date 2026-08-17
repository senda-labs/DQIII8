"""Per-format reopen-and-verify gates, run on the .tmp bytes BEFORE any
backup is taken or the original is replaced. A validation failure means:
tmp is discarded, original is untouched, no .bak is written.

Every gate validates against the INPUT's own integrity baseline, not an
absolute one — a pre-existing dangling relationship or oddity in the
source file must not be treated as newly-introduced corruption.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from lxml import etree

from .errors import ErrorClass, MetadataToolError

XML_PARSER = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    huge_tree=False,
    dtd_validation=False,
    load_dtd=False,
)


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def parse_xml_hardened(data: bytes):
    return etree.fromstring(data, parser=XML_PARSER)


# ---------------------------------------------------------------- images ---


def validate_image_structural(original_bytes: bytes, new_bytes: bytes) -> None:
    """Safe-tier (non-recompressing) path: pixel data must be byte-identical."""
    from PIL import Image

    try:
        orig = Image.open(io.BytesIO(original_bytes))
        orig.load()
        new = Image.open(io.BytesIO(new_bytes))
        new.load()
    except Exception as e:  # noqa: BLE001
        raise MetadataToolError(ErrorClass.ENGINE_FAILURE, f"image reopen failed: {e}") from e

    if orig.size != new.size or orig.mode != new.mode:
        raise MetadataToolError(
            ErrorClass.ENGINE_FAILURE, "image size/mode changed by removal — refusing"
        )
    if sha256(orig.tobytes()) != sha256(new.tobytes()):
        raise MetadataToolError(
            ErrorClass.ENGINE_FAILURE, "decoded pixel bytes changed by removal — refusing"
        )


# ------------------------------------------------------------------- pdf ---


def validate_pdf(original_bytes: bytes, new_bytes: bytes, *, allow_recovered: bool) -> None:
    import pikepdf
    import pypdf

    try:
        new_pdf = pikepdf.open(io.BytesIO(new_bytes))
    except pikepdf.PasswordError as e:
        raise MetadataToolError(ErrorClass.ENCRYPTED_OR_SIGNED, "output is encrypted") from e
    except Exception as e:  # noqa: BLE001
        raise MetadataToolError(ErrorClass.ENGINE_FAILURE, f"pikepdf reopen failed: {e}") from e

    try:
        orig_pdf = pikepdf.open(io.BytesIO(original_bytes))
        orig_page_count = len(orig_pdf.pages)
    except pikepdf.PasswordError as e:
        raise MetadataToolError(ErrorClass.ENCRYPTED_OR_SIGNED, "input is encrypted") from e
    except Exception:  # noqa: BLE001
        orig_page_count = None  # baseline unavailable — skip page-count cross-check

    new_page_count = len(new_pdf.pages)
    if orig_page_count is not None and new_page_count != orig_page_count:
        raise MetadataToolError(
            ErrorClass.ENGINE_FAILURE,
            f"page count changed by removal ({orig_page_count} -> {new_page_count})",
        )

    missing_contents = [i for i, p in enumerate(new_pdf.pages) if "/Contents" not in p]
    if missing_contents:
        raise MetadataToolError(
            ErrorClass.ENGINE_FAILURE, f"pages lost /Contents: {missing_contents}"
        )

    try:
        orig_text_len = sum(len(p.extract_text() or "") for p in pypdf.PdfReader(io.BytesIO(original_bytes)).pages)
        new_text_len = sum(len(p.extract_text() or "") for p in pypdf.PdfReader(io.BytesIO(new_bytes)).pages)
    except Exception:  # noqa: BLE001
        return  # pypdf cross-check is best-effort; a pypdf-side failure isn't a removal defect

    if orig_text_len > 0 and new_text_len < orig_text_len * 0.9:
        raise MetadataToolError(
            ErrorClass.ENGINE_FAILURE,
            f"extracted text length dropped materially ({orig_text_len} -> {new_text_len})",
        )


# ----------------------------------------------------------------- ooxml ---


def _relationship_targets(zf: zipfile.ZipFile) -> set[str]:
    """Every part-relative Target resolved to an absolute in-zip part name,
    across package-root _rels/.rels and every <dir>/_rels/<name>.rels.
    TargetMode="External" relationships are intentionally excluded — they're
    never resolved against the package.
    """
    import posixpath

    targets: set[str] = set()
    for name in zf.namelist():
        base = posixpath.basename(name)
        dirn = posixpath.dirname(name)
        if base.endswith(".rels") and posixpath.basename(dirn) == "_rels":
            owner_dir = posixpath.dirname(dirn)
            try:
                root = parse_xml_hardened(zf.read(name))
            except Exception:  # noqa: BLE001
                continue
            for rel in root:
                if rel.get("TargetMode") == "External":
                    continue
                target = rel.get("Target", "")
                if not target:
                    continue
                resolved = posixpath.normpath(posixpath.join(owner_dir, target))
                targets.add(resolved.lstrip("/"))
    return targets


def validate_ooxml_structural(new_bytes: bytes, original_bytes: bytes | None = None) -> None:
    """OPC-spec-correct structural checks — Override must resolve, every
    part must be covered by Override-or-Default, a Default with zero
    matching parts is legal (not an error).

    Relationship-target resolution is checked against the INPUT's own
    integrity baseline when `original_bytes` is given: a target that was
    already dangling in the input (fmt_ooxml.py never "fixes" relationships
    outside its scope) must not be reported as newly broken by this tool's
    own output. Without `original_bytes`, falls back to a strict
    output-only check.
    """
    baseline_dangling: set[str] = set()
    if original_bytes is not None:
        try:
            obuf = io.BytesIO(original_bytes)
            if zipfile.is_zipfile(obuf):
                with zipfile.ZipFile(obuf) as ozf:
                    onames = set(ozf.namelist())
                    for target in _relationship_targets(ozf):
                        if target and target not in onames:
                            baseline_dangling.add(target)
        except Exception:  # noqa: BLE001
            pass  # a bad original can't establish a baseline; fall back to strict

    buf = io.BytesIO(new_bytes)
    if not zipfile.is_zipfile(buf):
        raise MetadataToolError(ErrorClass.ENGINE_FAILURE, "output is not a valid zip")

    with zipfile.ZipFile(buf) as zf:
        if zf.testzip() is not None:
            raise MetadataToolError(ErrorClass.ENGINE_FAILURE, "zip CRC check failed")

        names = set(zf.namelist())
        if "[Content_Types].xml" not in names:
            raise MetadataToolError(ErrorClass.ENGINE_FAILURE, "[Content_Types].xml missing")

        ct_root = parse_xml_hardened(zf.read("[Content_Types].xml"))
        ns = {"ct": "http://schemas.openxmlformats.org/package/2006/content-types"}
        overrides = {el.get("PartName").lstrip("/") for el in ct_root.findall("ct:Override", ns)}
        default_exts = {el.get("Extension").lower() for el in ct_root.findall("ct:Default", ns)}

        for part in overrides:
            if part not in names:
                raise MetadataToolError(
                    ErrorClass.ENGINE_FAILURE, f"Override PartName resolves to missing part: {part}"
                )

        parts = {n for n in names if n != "[Content_Types].xml" and not n.endswith("/")}
        for part in parts:
            ext = part.rsplit(".", 1)[-1].lower() if "." in part else ""
            if part in overrides:
                continue
            if ext in default_exts:
                continue
            raise MetadataToolError(
                ErrorClass.ENGINE_FAILURE,
                f"part not covered by any Override or Default: {part}",
            )

        # relationship resolution: every non-external Target must resolve to
        # an existing part, EXCEPT one already dangling in the input — a
        # pre-existing dangling relationship is a detection finding
        # (fmt_ooxml.py), not something this tool "fixes" or may treat as
        # newly broken.
        for target in _relationship_targets(zf):
            if target and target not in names and target not in baseline_dangling:
                raise MetadataToolError(
                    ErrorClass.ENGINE_FAILURE, f"relationship Target resolves to missing part: {target}"
                )


def validate_ooxml_reparse(new_bytes: bytes, subtype: str) -> None:
    """Final real-parser acceptance gate — reopen with the matching
    real-world library so a structurally-plausible-but-unopenable file
    (e.g. a python-docx/openpyxl-specific expectation this tool's own
    structural check doesn't know about) is still caught.
    """
    try:
        if subtype == "docx":
            import docx

            docx.Document(io.BytesIO(new_bytes))
        elif subtype == "xlsx":
            import openpyxl

            openpyxl.load_workbook(io.BytesIO(new_bytes))
        elif subtype == "pptx":
            import pptx

            pptx.Presentation(io.BytesIO(new_bytes))
    except Exception as e:  # noqa: BLE001
        raise MetadataToolError(
            ErrorClass.ENGINE_FAILURE, f"real-parser reopen failed ({subtype}): {e}"
        ) from e
