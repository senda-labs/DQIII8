"""OOXML (docx/xlsx/pptx) metadata detection, and removal for docx only.

xlsx/pptx are DETECTION ONLY this pass (see plan §OOXML de-scope) —
metadata_remove.py refuses to remove anything from them, always via
MetadataToolError(UNSUPPORTED).

docx safe tier: docProps/core.xml identity fields (creator, lastModifiedBy,
subject, keywords, description, category, contentStatus), docProps/app.xml
Company/Manager, docProps/custom.xml (whole part, if present),
docProps/thumbnail.* (whole part, if present), word/settings.xml
proofState/rsids-registry/attachedTemplate-external-target, word/people.xml
+ commentsExtended.xml + commentsIds.xml + commentsExtensible.xml (whole
parts, if present), w:ins/w:del/w:comment author attributes (anonymized in
place, dates kept), ZIP entry timestamps (zeroed to the DOS epoch minimum).

docx --all tier additionally: customXml/ parts, word/comments.xml (comment
TEXT, not just author metadata), per-element w:rsid* attributes throughout
document.xml. Tracked-change accept/reject (unwrapping w:ins/w:del content)
is NOT implemented — too semantically risky for this pass; --all only
removes the comments part and per-element rsid noise, and anonymizes
w:ins/w:del authorship (already done at the safe tier).

OPC-correctness (the exact bug this whole de-scope protects against):
removing a part means deleting the matching Content_Types Override AND
every Relationship (in the OWNING part's _rels file, or the package-root
_rels/.rels for docProps/*) that resolves to it — a Default with zero
remaining matching parts is left alone, never removed.
"""

from __future__ import annotations

import io
import posixpath
import zipfile
from dataclasses import replace
from lxml import etree

from .errors import ErrorClass, MetadataToolError
from .report import Finding
from .validate import parse_xml_hardened

CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CP_NS = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DC_NS = "http://purl.org/dc/elements/1.1/"
DCTERMS_NS = "http://purl.org/dc/terms/"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
EP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"

ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)

# Adversarial-input guards (ErrorClass.ADVERSARIAL) — checked against zip
# central-directory metadata only, BEFORE any member is decompressed, so a
# hostile archive is rejected without ever allocating the inflated bytes.
MAX_ZIP_MEMBER_BYTES = 200 * 1024 * 1024
MAX_ZIP_TOTAL_BYTES = 500 * 1024 * 1024
MAX_ZIP_RATIO = 200
MAX_ZIP_MEMBERS = 10_000


def guard_zip_metadata(zf: zipfile.ZipFile) -> None:
    """Adversarial-input guards evaluated purely from the central directory.

    Must run before ANY member is decompressed — including the
    `[Content_Types].xml` read that format detection performs — or a zip bomb
    is expanded by the very code meant to reject it.
    """
    infos = zf.infolist()
    if len(infos) > MAX_ZIP_MEMBERS:
        raise MetadataToolError(ErrorClass.ADVERSARIAL, f"zip has {len(infos)} members, exceeds cap")

    seen_names: set[str] = set()
    total_uncompressed = 0
    for info in infos:
        name = info.filename
        if name in seen_names:
            raise MetadataToolError(ErrorClass.ADVERSARIAL, f"duplicate zip entry name: {name}")
        seen_names.add(name)

        norm = posixpath.normpath(name)
        if name.startswith("/") or posixpath.isabs(name) or norm == ".." or norm.startswith("../"):
            raise MetadataToolError(ErrorClass.ADVERSARIAL, f"path-traversal/absolute entry name: {name}")

        if info.file_size > MAX_ZIP_MEMBER_BYTES:
            raise MetadataToolError(
                ErrorClass.ADVERSARIAL, f"member {name} declares {info.file_size} bytes, exceeds per-member cap"
            )

        total_uncompressed += info.file_size
        if total_uncompressed > MAX_ZIP_TOTAL_BYTES:
            raise MetadataToolError(ErrorClass.ADVERSARIAL, "zip declared uncompressed total exceeds cap")

        if info.compress_size > 1024 and info.file_size / max(info.compress_size, 1) > MAX_ZIP_RATIO:
            raise MetadataToolError(
                ErrorClass.ADVERSARIAL,
                f"member {name} exceeds decompression-ratio guard ({info.file_size}/{info.compress_size})",
            )


def _read_zip(raw: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        guard_zip_metadata(zf)
        return {n: zf.read(n) for n in zf.namelist()}


def _write_zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(entries.keys()):
            info = zipfile.ZipInfo(name, date_time=ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            zf.writestr(info, entries[name])
    return buf.getvalue()


def _owning_dir(part: str) -> str:
    return posixpath.dirname(part)


def _rels_path_for(part: str) -> str:
    d = _owning_dir(part)
    base = posixpath.basename(part)
    return posixpath.join(d, "_rels", f"{base}.rels") if d else posixpath.join("_rels", f"{base}.rels")


def _package_root_rels() -> str:
    return "_rels/.rels"


def inspect(path, raw: bytes, subtype: str) -> list[Finding]:
    from . import fmt_c2pa

    path_str = str(path)
    findings: list[Finding] = []
    try:
        entries = _read_zip(raw)
    except MetadataToolError as e:
        return [
            Finding(
                path_str, "ooxml", "<package>", "adversarial_input", "safe", "high", False, e.message,
                error_class=e.error_class,
            )
        ]
    except Exception as e:  # noqa: BLE001
        return [
            Finding(
                path_str, "ooxml", "<package>", "engine_error", "safe", "high", False, str(e),
                error_class=ErrorClass.ENGINE_FAILURE,
            )
        ]

    if "docProps/core.xml" in entries:
        try:
            root = parse_xml_hardened(entries["docProps/core.xml"])
            present = [child.tag.split("}")[-1] for child in root]
            identity = [
                t
                for t in present
                if t in ("creator", "lastModifiedBy", "subject", "keywords", "description", "category", "contentStatus")
            ]
            if identity:
                findings.append(Finding(path_str, "ooxml", "docProps/core.xml", "identity_properties", "safe", "notice", True, ",".join(identity)))
        except Exception:  # noqa: BLE001
            pass

    if "docProps/app.xml" in entries:
        try:
            root = parse_xml_hardened(entries["docProps/app.xml"])
            present = [child.tag.split("}")[-1] for child in root if child.tag.split("}")[-1] in ("Company", "Manager")]
            if present:
                findings.append(Finding(path_str, "ooxml", "docProps/app.xml", "identity_properties", "safe", "notice", True, ",".join(present)))
        except Exception:  # noqa: BLE001
            pass

    if "docProps/custom.xml" in entries:
        findings.append(Finding(path_str, "ooxml", "docProps/custom.xml", "custom_properties", "safe", "notice", True, ""))

    thumb = next((n for n in entries if n.startswith("docProps/thumbnail")), None)
    if thumb:
        findings.append(Finding(path_str, "ooxml", thumb, "thumbnail", "safe", "notice", True, ""))

    for xmp_name in ("docProps/core.xml",):
        try:
            findings += fmt_c2pa.detect_xmp_provenance(path_str, "ooxml", entries.get(xmp_name, b""))
        except Exception:  # noqa: BLE001
            pass

    if subtype == "docx":
        findings += _inspect_docx(path_str, entries)
    elif subtype == "xlsx":
        findings += _inspect_xlsx(path_str, entries)
    elif subtype == "pptx":
        findings += _inspect_pptx(path_str, entries)

    # remove() implements docx only; _transform raises UNSUPPORTED for every other
    # subtype. Advertising removable=True on an xlsx/pptx made the dry run promise a
    # removal that --apply could never perform. Same precedent as fmt_image's TIFF
    # gate. Applied here at the call site, not inside detect_xmp_provenance(), which
    # the PDF path shares and where a change would disable PDF removal too.
    if subtype != "docx":
        note = f"{subtype} removal not implemented — detection only; strip it with the authoring app"
        findings = [
            replace(f, removable=False, note=(f"{f.note} — {note}" if f.note else note))
            if f.removable
            else f
            for f in findings
        ]

    return findings


def _inspect_docx(path_str: str, entries: dict[str, bytes]) -> list[Finding]:
    findings: list[Finding] = []
    if "word/settings.xml" in entries:
        try:
            root = parse_xml_hardened(entries["word/settings.xml"])
            has_proof = root.find(f"{{{W_NS}}}proofState") is not None
            has_rsids = root.find(f"{{{W_NS}}}rsids") is not None
            attached = root.find(f"{{{W_NS}}}attachedTemplate")
            if has_proof or has_rsids:
                findings.append(Finding(path_str, "ooxml", "word/settings.xml", "editing_metadata", "safe", "notice", True, "proofState/rsids"))
            if attached is not None:
                findings.append(Finding(path_str, "ooxml", "word/settings.xml", "attached_template", "safe", "notice", True, "may reference an external template path"))
        except Exception:  # noqa: BLE001
            pass

    for part, label in (
        ("word/people.xml", "people"),
        ("word/commentsExtended.xml", "commentsExtended"),
        ("word/commentsIds.xml", "commentsIds"),
        ("word/commentsExtensible.xml", "commentsExtensible"),
    ):
        if part in entries:
            findings.append(Finding(path_str, "ooxml", part, "comment_metadata", "safe", "notice", True, label))

    if "word/document.xml" in entries:
        try:
            root = parse_xml_hardened(entries["word/document.xml"])
            authors = {el.get(f"{{{W_NS}}}author") for el in root.iter() if el.tag.split("}")[-1] in ("ins", "del")}
            authors.discard(None)
            if authors:
                findings.append(Finding(path_str, "ooxml", "word/document.xml", "tracked_change_authors", "safe", "notice", True, f"{len(authors)} distinct author(s)"))
            rsid_count = sum(1 for el in root.iter() if any(k.startswith(f"{{{W_NS}}}rsid") for k in el.attrib))
            if rsid_count:
                findings.append(Finding(path_str, "ooxml", "word/document.xml", "rsid_attributes", "all", "info", True, f"{rsid_count} element(s)"))
        except Exception:  # noqa: BLE001
            pass

    if "word/comments.xml" in entries:
        findings.append(Finding(path_str, "ooxml", "word/comments.xml", "comment_content", "all", "notice", True, ""))

    custom_xml_parts = [n for n in entries if n.startswith("customXml/") and n.endswith(".xml")]
    if custom_xml_parts:
        findings.append(Finding(path_str, "ooxml", "customXml/", "custom_xml", "all", "notice", True, f"{len(custom_xml_parts)} part(s)"))

    return findings


def _inspect_xlsx(path_str: str, entries: dict[str, bytes]) -> list[Finding]:
    findings = []
    persons = [n for n in entries if n.startswith("xl/persons/")]
    if persons:
        findings.append(Finding(path_str, "ooxml", "xl/persons/", "identity_properties", "safe", "notice", False, f"{len(persons)} part(s) — detection only, xlsx removal deferred"))
    tc = [n for n in entries if n.startswith("xl/threadedComments/")]
    if tc:
        findings.append(Finding(path_str, "ooxml", "xl/threadedComments/", "comment_metadata", "safe", "notice", False, f"{len(tc)} part(s) — detection only"))
    ext_links = [n for n in entries if n.startswith("xl/externalLinks/_rels/")]
    if ext_links:
        findings.append(Finding(path_str, "ooxml", "xl/externalLinks/_rels/", "external_link_paths", "safe", "notice", False, "detection only"))
    if "xl/workbook.xml" in entries:
        try:
            root = parse_xml_hardened(entries["xl/workbook.xml"])
            if root.find(".//{*}fileVersion") is not None:
                findings.append(Finding(path_str, "ooxml", "xl/workbook.xml", "file_version", "safe", "notice", False, "detection only"))
        except Exception:  # noqa: BLE001
            pass
    return findings


def _inspect_pptx(path_str: str, entries: dict[str, bytes]) -> list[Finding]:
    findings = []
    if "ppt/authors.xml" in entries:
        findings.append(Finding(path_str, "ooxml", "ppt/authors.xml", "identity_properties", "safe", "notice", False, "detection only, pptx removal deferred"))
    slide_comments = [n for n in entries if n.startswith("ppt/slides/") and "comment" in n.lower()]
    if slide_comments:
        findings.append(Finding(path_str, "ooxml", "ppt/slides/*comments*", "comment_metadata", "safe", "notice", False, f"{len(slide_comments)} part(s) — detection only"))
    return findings


# -------------------------------------------------------------- removal ---


def _load_content_types(entries: dict[str, bytes]):
    return parse_xml_hardened(entries["[Content_Types].xml"])


def _remove_part(entries: dict[str, bytes], ct_root, part: str) -> None:
    """Removes `part` from the package: the entry itself, its Content_Types
    Override (if any — never touches a Default), and every Relationship
    resolving to it across all _rels files (package-root and part-owned).
    """
    if part not in entries:
        return
    del entries[part]

    for ov in ct_root.findall(f"{{{CT_NS}}}Override"):
        if ov.get("PartName", "").lstrip("/") == part:
            ct_root.remove(ov)

    for rels_name in [n for n in list(entries.keys()) if n.endswith(".rels")]:
        base = posixpath.basename(rels_name)
        dirn = posixpath.dirname(rels_name)
        if base.endswith(".rels") and posixpath.basename(dirn) == "_rels":
            owner_dir = posixpath.dirname(dirn)
        elif rels_name == "_rels/.rels":
            owner_dir = ""
        else:
            continue
        try:
            rroot = parse_xml_hardened(entries[rels_name])
        except Exception:  # noqa: BLE001
            continue
        changed = False
        for rel in list(rroot):
            if rel.get("TargetMode") == "External":
                continue
            target = rel.get("Target", "")
            if not target:
                continue
            resolved = posixpath.normpath(posixpath.join(owner_dir, target)).lstrip("/")
            if resolved == part:
                rroot.remove(rel)
                changed = True
        if changed:
            entries[rels_name] = etree.tostring(rroot, xml_declaration=True, encoding="UTF-8", standalone=True)


def _strip_element(root, ns: str, local_name: str) -> bool:
    changed = False
    for el in list(root.iter(f"{{{ns}}}{local_name}")):
        el.getparent().remove(el)
        changed = True
    return changed


def _clear_core_props(entries: dict[str, bytes]) -> None:
    if "docProps/core.xml" not in entries:
        return
    root = parse_xml_hardened(entries["docProps/core.xml"])
    for ns, local in (
        (DC_NS, "creator"),
        (CP_NS, "lastModifiedBy"),
        (DC_NS, "subject"),
        (CP_NS, "keywords"),
        (DC_NS, "description"),
        (CP_NS, "category"),
        (CP_NS, "contentStatus"),
    ):
        _strip_element(root, ns, local)
    entries["docProps/core.xml"] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _clear_app_props(entries: dict[str, bytes]) -> None:
    if "docProps/app.xml" not in entries:
        return
    root = parse_xml_hardened(entries["docProps/app.xml"])
    for local in ("Company", "Manager"):
        _strip_element(root, EP_NS, local)
    entries["docProps/app.xml"] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _clear_settings(entries: dict[str, bytes]) -> None:
    if "word/settings.xml" not in entries:
        return
    root = parse_xml_hardened(entries["word/settings.xml"])
    _strip_element(root, W_NS, "proofState")
    _strip_element(root, W_NS, "rsids")
    _strip_element(root, W_NS, "attachedTemplate")
    entries["word/settings.xml"] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _anonymize_authors(entries: dict[str, bytes]) -> None:
    for part in ("word/document.xml", "word/comments.xml"):
        if part not in entries:
            continue
        root = parse_xml_hardened(entries[part])
        changed = False
        for el in root.iter():
            tag = el.tag.split("}")[-1]
            if tag in ("ins", "del", "comment"):
                attr = f"{{{W_NS}}}author"
                if attr in el.attrib and el.attrib[attr]:
                    el.attrib[attr] = ""
                    changed = True
        if changed:
            entries[part] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _strip_rsid_attrs(entries: dict[str, bytes]) -> None:
    if "word/document.xml" not in entries:
        return
    root = parse_xml_hardened(entries["word/document.xml"])
    changed = False
    for el in root.iter():
        for key in [k for k in el.attrib if k.startswith(f"{{{W_NS}}}rsid")]:
            del el.attrib[key]
            changed = True
    if changed:
        entries["word/document.xml"] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def remove(raw: bytes, *, all_tier: bool) -> bytes:
    from . import fmt_c2pa

    try:
        entries = _read_zip(raw)
    except MetadataToolError:
        raise  # adversarial classification must survive, not be downgraded to CORRUPT
        # (CORRUPT is acceptable with --all --yes; ADVERSARIAL must never be)
    except Exception as e:  # noqa: BLE001
        raise MetadataToolError(ErrorClass.CORRUPT, f"not a valid zip: {e}") from e

    if "[Content_Types].xml" not in entries:
        raise MetadataToolError(ErrorClass.CORRUPT, "[Content_Types].xml missing")

    ct_root = _load_content_types(entries)

    _clear_core_props(entries)
    _clear_app_props(entries)
    _clear_settings(entries)
    _anonymize_authors(entries)

    if "docProps/core.xml" in entries:
        try:
            xmp_findings = fmt_c2pa.detect_xmp_provenance("", "ooxml", entries["docProps/core.xml"])
            if xmp_findings:
                root = parse_xml_hardened(entries["docProps/core.xml"])
                _strip_element(root, DCTERMS_NS, "provenance")
                entries["docProps/core.xml"] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        except Exception:  # noqa: BLE001
            pass

    for part in list(entries.keys()):
        if part == "docProps/custom.xml":
            _remove_part(entries, ct_root, part)
        elif part.startswith("docProps/thumbnail"):
            _remove_part(entries, ct_root, part)
        elif part in (
            "word/people.xml",
            "word/commentsExtended.xml",
            "word/commentsIds.xml",
            "word/commentsExtensible.xml",
        ):
            _remove_part(entries, ct_root, part)

    if all_tier:
        for part in [n for n in list(entries.keys()) if n.startswith("customXml/")]:
            _remove_part(entries, ct_root, part)
        if "word/comments.xml" in entries:
            _remove_part(entries, ct_root, "word/comments.xml")
        _strip_rsid_attrs(entries)

    entries["[Content_Types].xml"] = etree.tostring(ct_root, xml_declaration=True, encoding="UTF-8", standalone=True)
    return _write_zip(entries)
