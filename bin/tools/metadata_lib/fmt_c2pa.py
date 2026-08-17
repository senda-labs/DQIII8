"""C2PA content-credentials manifest detection (all carriers) and removal
(JPEG/PNG/WebP/PDF only — BMFF is detection-only, see module docstring below).

Verified against C2PA Technical Specification 2.4 + c2pa-rs carrier
locations:
  JPEG   APP11 segment(s), JUMBF box, type UUID 63327061-0011-0010-8000-
         00AA00389B71 identifies a C2PA JUMBF box (matched by searching for
         the UUID bytes near the start of the reassembled JUMBF span, since
         the exact sub-box nesting offset is secondhand-verified against
         c2pa-rs/community docs, not the paywalled ISO/IEC 19566-5 spec
         text). Continuation segments repeat the full CI/En/Z header and are
         grouped by identical En + contiguous ascending Z as one physically
         contiguous span.
  PNG    caBX ancillary chunk (unregistered-by-convention). No spec-stated
         max count — every caBX chunk found is a finding; >1 is also
         reported as an anomaly.
  WebP   RIFF sub-chunk FourCC "C2PA" inside the top-level RIFF container.
  BMFF   uuid box, UUID d8fec3d6-1b0e-483c-9297-5828877ec481. DETECTION
         ONLY: manifests are referenced by absolute byte offsets elsewhere
         in the container (merkle boxes, iloc/stco/co64/tfhd/sidx/saio);
         correct removal needs offset-preserving in-place `free`-box
         substitution, not implemented this pass.
  PDF    any indirect object carrying /AF with /AFRelationship
         /C2PA_Manifest and/or /Subtype /application#2Fc2pa — not just
         objects reachable from /Catalog/AF, since PDF permits multiple
         manifest stores (one per incremental update) and object-level
         manifests on any stream/dictionary.
  XMP    dcterms:provenance — a pointer to an EXTERNAL manifest, detected
         and removable independently of any embedded store; reported as
         its own finding type so removing only the embedded store can never
         be mistaken for full removal.

Mandatory disclosure on every finding: soft binding (a durable pixel-domain
fingerprint resolved via a cloud registry) survives manifest removal —
report "embedded manifest removed", never "provenance removed".
"""

from __future__ import annotations

import struct

from .report import C2PA_SOFT_BINDING_NOTE, Finding

JUMBF_TYPE_UUID = bytes.fromhex("6332706100110010800000aa00389b71")  # spells "c2pa" + fixed suffix
BMFF_C2PA_UUID = bytes.fromhex("d8fec3d61b0e483c92975828877ec481")
APP11_MARKER = 0xFFEB


# --------------------------------------------------------------- helpers ---


def _iter_jpeg_segments(data: bytes):
    """Yield (marker, seg_start, payload_start, payload_end) for each JPEG
    marker segment. seg_start is the offset of the 0xFF marker byte.
    """
    i = 0
    n = len(data)
    if not data.startswith(b"\xff\xd8"):
        return
    i = 2
    while i + 4 <= n:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = (data[i] << 8) | data[i + 1]
        if marker in (0xFFD8, 0xFFD9) or 0xFFD0 <= marker <= 0xFFD7:
            i += 2
            continue
        if i + 4 > n:
            break
        seg_len = struct.unpack(">H", data[i + 2 : i + 4])[0]
        payload_start = i + 4
        payload_end = i + 2 + seg_len
        if payload_end > n:
            break
        yield marker, i, payload_start, payload_end
        if marker == 0xFFDA:  # start-of-scan: rest is entropy-coded data, stop
            break
        i = payload_end


def _app11_spans(data: bytes) -> list[tuple[int, int, int, int]]:
    """(seg_start, seg_end_exclusive, En, Z) for every JP-boxed APP11 segment."""
    spans: list[tuple[int, int, int, int]] = []
    for marker, seg_start, pstart, pend in _iter_jpeg_segments(data):
        if marker != APP11_MARKER:
            continue
        payload = data[pstart:pend]
        if len(payload) < 8 or payload[0:2] != b"JP":
            continue
        en = struct.unpack(">H", payload[2:4])[0]
        z = struct.unpack(">I", payload[4:8])[0]
        spans.append((seg_start, pend, en, z))
    spans.sort(key=lambda t: t[0])
    return spans


def _c2pa_app11_groups(data: bytes) -> list[tuple[int, int]]:
    """Byte ranges of C2PA-carrying APP11 runs.

    A run is extended only by the *immediately adjacent* next segment with the
    same En and Z+1. Skipping over intervening segments (the previous
    behaviour) made a group span cover unrelated APP segments sitting between
    two C2PA ones, so deleting the group destroyed innocent data — and the
    detection report understated how many separate manifests were present.
    """
    spans = _app11_spans(data)
    groups: list[tuple[int, int]] = []
    idx = 0
    while idx < len(spans):
        start, end, en, z = spans[idx]
        last = idx
        expect_z = z + 1
        while last + 1 < len(spans):
            s2, e2, en2, z2 = spans[last + 1]
            if s2 != end or en2 != en or z2 != expect_z:
                break
            end = e2
            expect_z += 1
            last += 1
        blob = data[start:end]
        if JUMBF_TYPE_UUID in blob[: min(len(blob), 512)]:
            groups.append((start, end))
        idx = last + 1
    return groups


def detect_jpeg_c2pa(path_str: str, data: bytes) -> list[Finding]:
    return [
        Finding(
            path=path_str,
            format="jpeg",
            location=f"APP11[{group_start}:{group_end}]",
            field="c2pa_manifest",
            tier="safe",
            severity="high",
            removable=True,
            note=C2PA_SOFT_BINDING_NOTE,
        )
        for group_start, group_end in _c2pa_app11_groups(data)
    ]


def remove_jpeg_c2pa(data: bytes) -> bytes:
    """Deletes every C2PA-carrying APP11 run (as grouped above) entirely."""
    to_delete = _c2pa_app11_groups(data)

    if not to_delete:
        return data

    to_delete.sort()
    out = bytearray()
    cursor = 0
    for start, end in to_delete:
        out += data[cursor:start]
        cursor = end
    out += data[cursor:]
    return bytes(out)


def detect_png_c2pa(path_str: str, data: bytes) -> list[Finding]:
    findings: list[Finding] = []
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return findings
    i = 8
    n = len(data)
    count = 0
    while i + 8 <= n:
        length = struct.unpack(">I", data[i : i + 4])[0]
        ctype = data[i + 4 : i + 8]
        chunk_end = i + 8 + length + 4
        if chunk_end > n:
            break
        if ctype == b"caBX":
            count += 1
            findings.append(
                Finding(
                    path=path_str,
                    format="png",
                    location=f"caBX@{i}",
                    field="c2pa_manifest",
                    tier="safe",
                    severity="high",
                    removable=True,
                    note=C2PA_SOFT_BINDING_NOTE
                    + (" (multiple caBX chunks present — anomaly)" if count > 1 else ""),
                )
            )
        i = chunk_end
    return findings


def remove_png_c2pa(data: bytes) -> bytes:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return data
    out = bytearray(data[:8])
    i = 8
    n = len(data)
    while i + 8 <= n:
        length = struct.unpack(">I", data[i : i + 4])[0]
        ctype = data[i + 4 : i + 8]
        chunk_end = i + 8 + length + 4
        if chunk_end > n:
            out += data[i:]
            break
        if ctype != b"caBX":
            out += data[i:chunk_end]
        i = chunk_end
    return bytes(out)


def _riff_chunks(data: bytes):
    """Yield (fourcc, data_start, data_end, chunk_start, chunk_end_incl_pad)
    for the top-level RIFF sub-chunks of a WebP file."""
    if len(data) < 12 or data[0:4] != b"RIFF" or data[8:12] != b"WEBP":
        return
    i = 12
    n = len(data)
    while i + 8 <= n:
        fourcc = data[i : i + 4]
        size = struct.unpack("<I", data[i + 4 : i + 8])[0]
        data_start = i + 8
        data_end = data_start + size
        padded_end = data_end + (size & 1)
        if data_end > n:
            break
        yield fourcc, data_start, data_end, i, min(padded_end, n)
        i = padded_end


def detect_webp_c2pa(path_str: str, data: bytes) -> list[Finding]:
    findings = []
    for fourcc, _ds, _de, cs, _ce in _riff_chunks(data):
        if fourcc == b"C2PA":
            findings.append(
                Finding(
                    path=path_str,
                    format="webp",
                    location=f"RIFF/C2PA@{cs}",
                    field="c2pa_manifest",
                    tier="safe",
                    severity="high",
                    removable=True,
                    note=C2PA_SOFT_BINDING_NOTE,
                )
            )
    return findings


def remove_webp_c2pa(data: bytes) -> bytes:
    chunks = list(_riff_chunks(data))
    if not any(fourcc == b"C2PA" for fourcc, *_ in chunks):
        return data
    body = bytearray()
    for fourcc, _ds, _de, cs, ce in chunks:
        if fourcc == b"C2PA":
            continue
        body += data[cs:ce]
    new_riff_size = 4 + len(body)  # "WEBP" + chunks
    out = bytearray(b"RIFF")
    out += struct.pack("<I", new_riff_size)
    out += b"WEBP"
    out += body
    return bytes(out)


def detect_bmff_c2pa(path_str: str, data: bytes) -> list[Finding]:
    """Detection only — top-level box walk, no dependency needed."""
    findings = []
    if len(data) < 8 or data[4:8] != b"ftyp":
        return findings
    i = 0
    n = len(data)
    while i + 8 <= n:
        size = struct.unpack(">I", data[i : i + 4])[0]
        btype = data[i + 4 : i + 8]
        header_len = 8
        if size == 1:
            if i + 16 > n:
                break
            size = struct.unpack(">Q", data[i + 8 : i + 16])[0]
            header_len = 16
        if size == 0:
            box_end = n
        else:
            box_end = i + size
        if btype == b"uuid" and i + header_len + 16 <= n:
            box_uuid = data[i + header_len : i + header_len + 16]
            if box_uuid == BMFF_C2PA_UUID:
                findings.append(
                    Finding(
                        path=path_str,
                        format="bmff",
                        location=f"uuid@{i}",
                        field="c2pa_manifest",
                        tier="safe",
                        severity="high",
                        removable=False,
                        note=C2PA_SOFT_BINDING_NOTE
                        + " (BMFF removal not implemented — offset-preserving substitution "
                        "required; detect-only this pass)",
                    )
                )
        if box_end <= i:
            break
        i = box_end
    return findings


def detect_pdf_c2pa(path_str: str, pdf) -> list[Finding]:
    """pdf is an open pikepdf.Pdf. Iterates ALL indirect objects for /AF —
    not just those reachable from /Catalog/AF — since PDF permits object-
    level manifests and multiple manifest stores across incremental updates.
    """
    import pikepdf

    findings: list[Finding] = []
    seen_ids = set()
    for obj in pdf.objects:
        try:
            if not isinstance(obj, pikepdf.Dictionary) and not isinstance(obj, pikepdf.Stream):
                continue
            is_manifest = False
            if "/AFRelationship" in obj and str(obj.get("/AFRelationship")) == "/C2PA_Manifest":
                is_manifest = True
            subtype = obj.get("/Subtype") if "/Subtype" in obj else None
            if subtype is not None and "c2pa" in str(subtype).lower():
                is_manifest = True
            if is_manifest:
                # .objgen is the PDF object's stable (num, gen) identity;
                # id() is a CPython address that can be reused across GC'd
                # per-iteration wrapper objects, so it could dedup two
                # genuinely distinct manifests into one finding.
                oid = getattr(obj, "objgen", None) or ("addr", id(obj))
                if oid in seen_ids:
                    continue
                seen_ids.add(oid)
                findings.append(
                    Finding(
                        path=path_str,
                        format="pdf",
                        location="indirect-object/AF",
                        field="c2pa_manifest",
                        tier="safe",
                        severity="high",
                        removable=True,
                        note=C2PA_SOFT_BINDING_NOTE,
                    )
                )
        except Exception:  # noqa: BLE001 - malformed individual object, skip it
            continue
    return findings


def detect_xmp_provenance(path_str: str, fmt: str, xmp_bytes: bytes) -> list[Finding]:
    if not xmp_bytes or b"dcterms:provenance" not in xmp_bytes:
        return []
    return [
        Finding(
            path=path_str,
            format=fmt,
            location="XMP/dcterms:provenance",
            field="external_manifest_pointer",
            tier="safe",
            severity="high",
            removable=True,
            note="points at an EXTERNAL C2PA manifest — removing only an embedded "
            "manifest store while leaving this pointer would falsely imply full removal.",
        )
    ]
