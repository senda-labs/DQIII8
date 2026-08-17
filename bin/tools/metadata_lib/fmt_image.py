"""EXIF/IPTC/XMP detection and removal for JPEG/PNG/WebP/TIFF.

Primary engine is exiftool, invoked through a hardened temp-copy driver
(§exiftool hardening): the caller-controlled path never reaches argv, so a
crafted filename (leading '-', embedded '-tagsFromFile', newline, non-ASCII)
cannot inject flags or read arbitrary files. When exiftool is absent, a
narrower pure-Python fallback strips the same identity-bearing carriers
(JPEG APP1/EXIF+APP13/IPTC, PNG eXIf+tEXt/iTXt/zTXt, WebP EXIF/XMP RIFF
chunks) — reported as "degraded" since it can't reach XMP-namespace-level
granularity the way exiftool can.

Safe tier clears the EXIF/IPTC/XMP/GPS groups wholesale (identity, device,
location) while leaving ICC_Profile and pixel data untouched. --all tier
additionally clears ICC_Profile and PNG text chunks.
"""

from __future__ import annotations

import os
import resource
import shutil
import struct
import subprocess
import tempfile

from .errors import ErrorClass
from .report import Finding

EXIFTOOL_TIMEOUT = 30
# The ONE search space for exiftool. The availability check and the actual
# execution must resolve against exactly the same PATH, or "available" can be
# true while every invocation fails — which used to be swallowed into a silent
# false-clean, the worst failure mode for a privacy tool.
EXIFTOOL_PATH = "/usr/bin:/bin"
_SAFE_CLEAR_ARGS = ["-EXIF:all=", "-IPTC:all=", "-XMP:all=", "-GPS:all="]
_ALL_EXTRA_CLEAR_ARGS = ["-ICC_Profile:all=", "-PNG:all="]

_EXT_BY_FMT = {"jpeg": ".jpg", "png": ".png", "webp": ".webp", "tiff": ".tiff"}

# exiftool's "PNG" group bundles IHDR/gAMA/cHRM-derived structural facts
# together with actual tEXt/iTXt/zTXt keyword tags — only the latter are
# removable text-chunk content (--all tier, per the module docstring).
_PNG_STRUCTURAL_TAGS = {
    "ImageWidth", "ImageHeight", "BitDepth", "ColorType", "Compression",
    "Filter", "Interlace", "Gamma", "WhitePoint", "RedX", "RedY", "GreenX",
    "GreenY", "BlueX", "BlueY", "SRGBRendering", "PixelsPerUnitX",
    "PixelsPerUnitY", "PixelUnits", "BackgroundColor", "Transparency",
    "SignificantBits", "LastModifyDate",
}


def resolve_exiftool() -> str | None:
    """Absolute path to exiftool as it will actually be executed, or None."""
    return shutil.which("exiftool", path=EXIFTOOL_PATH)


def exiftool_available() -> bool:
    return resolve_exiftool() is not None


def _preexec_limits():
    def _set():
        resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))  # 1 GiB
        resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))

    return _set


def _run_exiftool_on_copy(raw: bytes, fmt: str, extra_args: list[str]) -> bytes:
    """Copies raw bytes into a fixed-name temp file (never the caller's real
    path) and runs exiftool against that copy only. Returns the resulting
    bytes. Raises subprocess.SubprocessError/OSError on failure — caller
    classifies as ErrorClass.ENGINE_FAILURE.
    """
    exe = resolve_exiftool()
    if exe is None:
        raise OSError(f"exiftool not found on {EXIFTOOL_PATH}")
    ext = _EXT_BY_FMT.get(fmt, "")
    with tempfile.TemporaryDirectory(prefix=".mdimg-") as tmpdir:
        in_path = os.path.join(tmpdir, f"in{ext}")
        with open(in_path, "wb") as fh:
            fh.write(raw)

        cmd = [
            exe,
            "-config",
            "/dev/null",
            "-q",
            "-q",
            "-m",
            "-P",
            "-overwrite_original",
            *extra_args,
            in_path,
        ]
        env = {"PATH": EXIFTOOL_PATH, "HOME": tmpdir, "EXIFTOOL_HOME": tmpdir}
        result = subprocess.run(
            cmd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=EXIFTOOL_TIMEOUT,
            preexec_fn=_preexec_limits(),
            cwd=tmpdir,
        )
        if result.returncode != 0:
            raise subprocess.SubprocessError(
                f"exiftool exit {result.returncode}: {result.stderr.decode('utf-8', 'replace')[:300]}"
            )
        with open(in_path, "rb") as fh:
            return fh.read()


def _list_tags_via_exiftool(raw: bytes, fmt: str) -> list[tuple[str, str]]:
    """Returns [(group:tag, ...)] present in the image, values never read
    into the result — only tag identity, per the audit-log no-value rule.
    """
    import json

    exe = resolve_exiftool()
    if exe is None:
        raise OSError(f"exiftool not found on {EXIFTOOL_PATH}")
    ext = _EXT_BY_FMT.get(fmt, "")
    with tempfile.TemporaryDirectory(prefix=".mdimg-") as tmpdir:
        in_path = os.path.join(tmpdir, f"in{ext}")
        with open(in_path, "wb") as fh:
            fh.write(raw)
        cmd = [exe, "-config", "/dev/null", "-j", "-G1", "-a", "-s", in_path]
        env = {"PATH": EXIFTOOL_PATH, "HOME": tmpdir, "EXIFTOOL_HOME": tmpdir}
        result = subprocess.run(
            cmd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=EXIFTOOL_TIMEOUT,
            preexec_fn=_preexec_limits(),
            cwd=tmpdir,
        )
        # An engine failure must NEVER degrade to "no tags found" — that is a
        # silent false-clean. Raise; inspect() turns it into an engine_error
        # Finding carrying ErrorClass.ENGINE_FAILURE.
        if result.returncode != 0:
            raise subprocess.SubprocessError(
                f"exiftool exit {result.returncode}: {result.stderr.decode('utf-8', 'replace')[:300]}"
            )
        try:
            data = json.loads(result.stdout.decode("utf-8", "replace"))
        except Exception as e:  # noqa: BLE001
            raise subprocess.SubprocessError(f"exiftool emitted unparseable JSON: {e}") from e
        if not data:
            return []
        out = []
        for key in data[0].keys():
            if key in ("SourceFile",):
                continue
            if ":" in key:
                group, tag = key.split(":", 1)
            else:
                group, tag = "File", key
            out.append((group, tag))
        return out


_IDENTITY_GROUPS = {"EXIF", "IPTC", "XMP", "GPS", "ExifIFD", "IFD0", "IFD1"}


def _is_identity_group(group: str) -> bool:
    """`-G1` returns namespace-qualified XMP families (XMP-dc, XMP-photoshop,
    XMP-x, ...) and never the bare string "XMP", so an exact-set match alone
    meant XMP was silently never flagged regardless of what was embedded.
    """
    return group in _IDENTITY_GROUPS or group.startswith("XMP-")


def inspect(path, raw: bytes, fmt: str) -> list[Finding]:
    """Read-only detection. Uses exiftool -j when available (names only,
    never values); pure-Python magic-byte carrier scan otherwise.
    """
    path_str = str(path)
    findings: list[Finding] = []
    # metadata_remove._transform has no TIFF branch (it raises UNSUPPORTED,
    # exit 0). Claiming removable=True made --apply on a TIFF report as if it
    # had stripped something while silently changing nothing.
    removable = fmt != "tiff"
    tiff_note = " — TIFF removal not implemented, detection only" if fmt == "tiff" else ""

    if exiftool_available():
        try:
            tags = _list_tags_via_exiftool(raw, fmt)
        except Exception as e:  # noqa: BLE001
            # Never collapse an engine failure into an empty (== "clean")
            # result. This finding is non-removable and carries the structured
            # ErrorClass so metadata_remove.py aborts with the engine_failure
            # exit code instead of reporting success.
            return [
                Finding(
                    path=path_str,
                    format=fmt,
                    location="<exiftool>",
                    field="engine_error",
                    tier="safe",
                    severity="high",
                    removable=False,
                    note=f"exiftool detection failed: {e}",
                    error_class=ErrorClass.ENGINE_FAILURE,
                )
            ]
        by_group: dict[str, int] = {}
        png_text_tags = 0
        jpeg_comment = False
        for group, tag in tags:
            if group == "PNG" and tag not in _PNG_STRUCTURAL_TAGS:
                png_text_tags += 1
                continue
            # A JPEG COM segment is free text that routinely carries author names
            # and tool strings, but exiftool buckets it under the catch-all "File"
            # group, which _is_identity_group rejects — so it was reported clean
            # and survived --apply. Gate on the tag, never on the group: "File"
            # also holds FileSize/FileType/MIMEType/ImageWidth.
            if fmt == "jpeg" and tag == "Comment":
                jpeg_comment = True
                continue
            by_group[group] = by_group.get(group, 0) + 1
        if jpeg_comment:
            findings.append(
                Finding(
                    path=path_str,
                    format=fmt,
                    location="JPEG:COM",
                    field="jpeg_comment",
                    tier="safe",
                    severity="notice",
                    removable=removable,
                    note="free-text comment segment",
                )
            )
        for group, count in sorted(by_group.items()):
            if _is_identity_group(group):
                findings.append(
                    Finding(
                        path=path_str,
                        format=fmt,
                        location=group,
                        field="identity_metadata",
                        tier="safe",
                        severity="notice",
                        removable=removable,
                        note=f"{count} tag(s){tiff_note}",
                    )
                )
            elif group == "ICC_Profile":
                findings.append(
                    Finding(
                        path=path_str,
                        format=fmt,
                        location=group,
                        field="icc_profile",
                        tier="all",
                        severity="info",
                        removable=removable,
                        note=f"{count} tag(s) — content-adjacent, --all tier{tiff_note}",
                    )
                )
        if png_text_tags:
            findings.append(
                Finding(
                    path=path_str,
                    format=fmt,
                    location="PNG",
                    field="text_chunk",
                    tier="all",
                    severity="info",
                    removable=True,
                    note=f"{png_text_tags} tag(s) — text chunk, content-adjacent, --all tier",
                )
            )
        return findings

    return _inspect_fallback(path_str, raw, fmt)


def _inspect_fallback(path_str: str, raw: bytes, fmt: str) -> list[Finding]:
    findings: list[Finding] = []
    if fmt == "jpeg":
        for marker, seg_start, pstart, pend in _iter_jpeg_app_segments(raw):
            payload = raw[pstart:pend]
            if marker == 0xFFE1 and (payload.startswith(b"Exif\x00\x00") or payload.startswith(b"http://ns.adobe.com/xap")):
                kind = "EXIF" if payload.startswith(b"Exif") else "XMP"
                findings.append(
                    Finding(path_str, "jpeg", f"APP1@{seg_start}", "identity_metadata", "safe", "notice", True, kind)
                )
            elif marker == 0xFFED and payload.startswith(b"Photoshop 3.0"):
                findings.append(
                    Finding(path_str, "jpeg", f"APP13@{seg_start}", "identity_metadata", "safe", "notice", True, "IPTC")
                )
            elif marker == 0xFFE2 and payload.startswith(b"ICC_PROFILE\x00"):
                findings.append(
                    Finding(path_str, "jpeg", f"APP2@{seg_start}", "icc_profile", "all", "info", True, "ICC")
                )
            elif marker == 0xFFFE:
                findings.append(
                    Finding(path_str, "jpeg", f"COM@{seg_start}", "jpeg_comment", "safe", "notice", True, "free-text comment segment")
                )
    elif fmt == "png":
        for ctype, start in _iter_png_chunk_types(raw):
            if ctype in (b"eXIf",):
                findings.append(Finding(path_str, "png", f"{ctype.decode()}@{start}", "identity_metadata", "safe", "notice", True, "EXIF"))
            elif ctype in _PNG_TEXT_CHUNKS:
                if _png_text_chunk_is_xmp(raw, start):
                    findings.append(Finding(path_str, "png", f"{ctype.decode()}@{start}", "identity_metadata", "safe", "notice", True, "XMP"))
                else:
                    findings.append(Finding(path_str, "png", f"{ctype.decode()}@{start}", "text_chunk", "all", "info", True, "text chunk, content-adjacent, --all tier"))
            elif ctype == b"iCCP":
                findings.append(Finding(path_str, "png", f"iCCP@{start}", "icc_profile", "all", "info", True, "ICC"))
    elif fmt == "webp":
        from .fmt_c2pa import _riff_chunks

        for fourcc, _ds, _de, cs, _ce in _riff_chunks(raw):
            if fourcc in (b"EXIF", b"XMP "):
                findings.append(Finding(path_str, "webp", f"{fourcc.strip().decode()}@{cs}", "identity_metadata", "safe", "notice", True, fourcc.strip().decode()))
            elif fourcc == b"ICCP":
                findings.append(Finding(path_str, "webp", f"ICCP@{cs}", "icc_profile", "all", "info", True, "ICC"))
    elif fmt == "tiff":
        if len(raw) >= 8:
            findings.append(Finding(path_str, "tiff", "IFD0", "identity_metadata", "safe", "notice", False, "TIFF tags (pure-Python fallback cannot enumerate individually) — TIFF removal not implemented, detection only"))
    return findings


def _iter_jpeg_app_segments(data: bytes):
    i = 2
    n = len(data)
    if not data.startswith(b"\xff\xd8"):
        return
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
        pstart, pend = i + 4, i + 2 + seg_len
        if pend > n:
            break
        yield marker, i, pstart, pend
        if marker == 0xFFDA:
            break
        i = pend


_PNG_TEXT_CHUNKS = (b"tEXt", b"iTXt", b"zTXt")


def _png_text_chunk_is_xmp(raw: bytes, start: int) -> bool:
    """XMP travels inside an iTXt chunk keyed `XML:com.adobe.xmp`. It is
    identity metadata (safe tier); every other text chunk is content-adjacent
    (--all tier). Both the exiftool path and this fallback must agree on that
    split, or a `--apply` without `--all` silently removes what the report
    listed as an --all-tier finding.
    """
    if start + 8 > len(raw):
        return False
    length = struct.unpack(">I", raw[start : start + 4])[0]
    return raw[start + 8 : start + 8 + length].startswith(b"XML:com.adobe.xmp\x00")


def _iter_png_chunk_types(data: bytes):
    i = 8
    n = len(data)
    while i + 8 <= n:
        length = struct.unpack(">I", data[i : i + 4])[0]
        ctype = data[i + 4 : i + 8]
        chunk_end = i + 8 + length + 4
        if chunk_end > n:
            break
        yield ctype, i
        i = chunk_end


def remove(raw: bytes, fmt: str, *, all_tier: bool) -> bytes:
    """Returns cleaned bytes. Raises on engine failure (caller classifies)."""
    if exiftool_available():
        args = list(_SAFE_CLEAR_ARGS)
        # JPEG only. _SAFE_CLEAR_ARGS is shared by jpeg/png/webp, and a bare
        # "-Comment=" would delete a PNG tEXt/iTXt "Comment" chunk — which inspect()
        # classifies tier="all" — during a plain safe-tier --apply, breaking the
        # tier split documented in _remove_fallback below.
        if fmt == "jpeg":
            args.append("-Comment=")
        if all_tier:
            args += _ALL_EXTRA_CLEAR_ARGS
        return _run_exiftool_on_copy(raw, fmt, args)
    return _remove_fallback(raw, fmt, all_tier=all_tier)


def _remove_fallback(raw: bytes, fmt: str, *, all_tier: bool) -> bytes:
    if fmt == "jpeg":
        # 0xFFFE (COM) is a length-prefixed segment like the APPn ones, so the
        # generic walker yields it with correct bounds. Note the walker breaks at
        # SOS, so a COM placed after the scan is out of scope for both engines.
        drop_markers = {0xFFE1, 0xFFED, 0xFFFE}  # APP1 (EXIF/XMP), APP13 (IPTC), COM
        if all_tier:
            drop_markers.add(0xFFE2)  # APP2 (ICC)
        out = bytearray(raw[:2])
        for marker, seg_start, _pstart, pend in _iter_jpeg_app_segments(raw):
            # SOS and everything after it is copied verbatim by the tail append
            # below; emitting its header here too would duplicate it and produce
            # a JPEG that strict decoders reject.
            if marker == 0xFFDA:
                break
            if marker in drop_markers:
                continue
            out += raw[seg_start:pend]
        out += raw[_last_scan_offset(raw):]
        return bytes(out)
    if fmt == "png":
        drop = {b"eXIf"}
        if all_tier:
            drop.update(_PNG_TEXT_CHUNKS)
            drop.add(b"iCCP")
        out = bytearray(raw[:8])
        i = 8
        n = len(raw)
        while i + 8 <= n:
            length = struct.unpack(">I", raw[i : i + 4])[0]
            ctype = raw[i + 4 : i + 8]
            chunk_end = i + 8 + length + 4
            if chunk_end > n:
                out += raw[i:]
                break
            drop_this = ctype in drop or (
                ctype in _PNG_TEXT_CHUNKS and _png_text_chunk_is_xmp(raw, i)
            )
            if not drop_this:
                out += raw[i:chunk_end]
            i = chunk_end
        return bytes(out)
    if fmt == "webp":
        from .fmt_c2pa import _riff_chunks
        import struct as _struct

        drop = {b"EXIF", b"XMP "}
        if all_tier:
            drop.add(b"ICCP")
        chunks = list(_riff_chunks(raw))
        body = bytearray()
        for fourcc, _ds, _de, cs, ce in chunks:
            if fourcc in drop:
                continue
            body += raw[cs:ce]
        out = bytearray(b"RIFF")
        out += _struct.pack("<I", 4 + len(body))
        out += b"WEBP"
        out += body
        return bytes(out)
    return raw


def _last_scan_offset(data: bytes) -> int:
    for marker, seg_start, _pstart, _pend in _iter_jpeg_app_segments(data):
        if marker == 0xFFDA:
            return seg_start
    return len(data)
