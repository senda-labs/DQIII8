"""Magic-byte format sniffing. Never trusts the extension for identity —
only for a mismatch check (refuse, never guess).

OOXML subtype is resolved from [Content_Types].xml's root-document Override
content-type, not the extension, so legitimate .docm/.xlsm/.pptm/.dotx/etc.
aren't wrongly refused just because they don't literally end in .docx.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from .errors import MetadataToolError

JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
PDF_MAGIC = b"%PDF-"
TIFF_MAGICS = (b"II*\x00", b"MM\x00*")

OOXML_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml": "docx",
    "application/vnd.ms-word.document.macroEnabled.main+xml": "docx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml": "docx",
    "application/vnd.ms-word.template.macroEnabledTemplate.main+xml": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml": "xlsx",
    "application/vnd.ms-excel.sheet.macroEnabled.main+xml": "xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.template.main+xml": "xlsx",
    "application/vnd.ms-excel.template.macroEnabled.main+xml": "xlsx",
    "application/vnd.ms-excel.sheet.binary.macroEnabled.main": "xlsb",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml": "pptx",
    "application/vnd.ms-powerpoint.presentation.macroEnabled.main+xml": "pptx",
    "application/vnd.openxmlformats-officedocument.presentationml.template.main+xml": "pptx",
    "application/vnd.ms-powerpoint.template.macroEnabled.main+xml": "pptx",
    "application/vnd.openxmlformats-officedocument.presentationml.slideshow.main+xml": "pptx",
    "application/vnd.ms-powerpoint.slideshow.macroEnabled.main+xml": "pptx",
}

EXTENSION_FAMILY = {
    ".docx": "docx", ".docm": "docx", ".dotx": "docx", ".dotm": "docx",
    ".xlsx": "xlsx", ".xlsm": "xlsx", ".xltx": "xlsx", ".xltm": "xlsx", ".xlsb": "xlsb",
    ".pptx": "pptx", ".pptm": "pptx", ".potx": "pptx", ".potm": "pptx",
    ".ppsx": "pptx", ".ppsm": "pptx",
}


class Detection:
    def __init__(self, fmt: str, subtype: str | None, mismatch: str | None):
        self.format = fmt  # "jpeg" | "png" | "webp" | "tiff" | "pdf" | "ooxml" | "bmff" | "unsupported"
        self.subtype = subtype  # for ooxml: "docx" | "xlsx" | "pptx" | "xlsb"
        self.mismatch = mismatch  # reason string if extension disagrees, else None


def _sniff_magic(data: bytes) -> str:
    if data.startswith(JPEG_MAGIC):
        return "jpeg"
    if data.startswith(PNG_MAGIC):
        return "png"
    if len(data) >= 12 and data[0:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data.startswith(TIFF_MAGICS):
        return "tiff"
    if data.startswith(PDF_MAGIC):
        return "pdf"
    if data[0:4] in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"):
        return "ooxml"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "bmff"
    return "unsupported"


def _ooxml_subtype(data: bytes) -> str | None:
    """Raises MetadataToolError(ADVERSARIAL) on a hostile package.

    The central-directory guards run before `[Content_Types].xml` is read, so
    detection never decompresses a member of a zip bomb, and a hostile package
    can never be quietly downgraded to "unclassified OPC" (which callers treat
    as an exit-0 skip).
    """
    from .fmt_ooxml import guard_zip_metadata

    try:
        import io

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            guard_zip_metadata(zf)
            if "[Content_Types].xml" not in zf.namelist():
                return None
            from lxml import etree

            root = etree.fromstring(
                zf.read("[Content_Types].xml"),
                parser=etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False),
            )
            ns = {"ct": "http://schemas.openxmlformats.org/package/2006/content-types"}
            for el in root.findall("ct:Override", ns):
                ct = el.get("ContentType", "")
                if ct in OOXML_CONTENT_TYPES:
                    return OOXML_CONTENT_TYPES[ct]
    except MetadataToolError:
        raise
    except Exception:  # noqa: BLE001
        return None
    return None


def detect(path: Path, data: bytes) -> Detection:
    fmt = _sniff_magic(data)
    subtype = None
    mismatch = None
    ext = path.suffix.lower()

    if fmt == "ooxml":
        subtype = _ooxml_subtype(data)
        if subtype is None:
            # a real OPC package we couldn't classify (ODF also matches PK
            # magic bytes and is explicitly out of scope) — report and skip,
            # not a hard mismatch since we genuinely don't know what it is.
            mismatch = None
        elif ext in EXTENSION_FAMILY and EXTENSION_FAMILY[ext] != subtype:
            mismatch = f"extension {ext} suggests {EXTENSION_FAMILY[ext]}, content-type says {subtype}"
    else:
        expected_exts = {
            "jpeg": (".jpg", ".jpeg"),
            "png": (".png",),
            "webp": (".webp",),
            "tiff": (".tif", ".tiff"),
            "pdf": (".pdf",),
        }.get(fmt)
        if expected_exts is not None and ext and ext not in expected_exts:
            mismatch = f"extension {ext} does not match detected format {fmt}"

    return Detection(fmt, subtype, mismatch)
