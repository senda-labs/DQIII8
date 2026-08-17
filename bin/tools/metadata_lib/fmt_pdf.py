"""PDF metadata detection and removal via pikepdf.

Safe tier: /Info, /Root/Metadata (XMP), per-page /Metadata, /Root/PieceInfo
+ per-page /PieceInfo, annotation /T (author names), C2PA manifest objects
(via fmt_c2pa.detect_pdf_c2pa), XMP dcterms:provenance pointer.

--all tier additionally: /Root/AcroForm field values, /Names/JavaScript,
/Root/OutputIntents, trailer /ID, and accepts a structurally-recovered
input that the safe tier refuses (see _requires_recovery below).

Full-rewrite save (pikepdf.Pdf.save with default settings) is what actually
drops incremental-update history — the core claim over `exiftool -all=`,
which only appends another incremental update and leaves prior revisions
byte-recoverable in the file.
"""

from __future__ import annotations

import io

from .errors import ErrorClass, MetadataToolError
from .report import Finding


def _requires_recovery(raw: bytes) -> bool:
    """True if pikepdf had to structurally repair the file to open it at
    all (broken xref, etc.) — detected by opening once with strict xref
    parsing off (pikepdf's default) and checking for a warning-worthy
    state via a second strict-ish open attempt using qpdf's own check.
    """
    import pikepdf

    try:
        with pikepdf.open(io.BytesIO(raw)) as pdf:
            # pikepdf/qpdf surfaces recovery via .Root presence + a linearization
            # or xref repair path; the reliable public signal is
            # Pdf.open(..., attempt_recovery=False) raising where the default
            # (attempt_recovery=True) would have succeeded.
            _ = pdf.Root
    except Exception:  # noqa: BLE001
        return True
    try:
        with pikepdf.open(io.BytesIO(raw), attempt_recovery=False):
            return False
    except Exception:  # noqa: BLE001
        return True


def _open(raw: bytes):
    import pikepdf

    try:
        return pikepdf.open(io.BytesIO(raw))
    except pikepdf.PasswordError as e:
        raise MetadataToolError(ErrorClass.ENCRYPTED_OR_SIGNED, "PDF is encrypted") from e
    except Exception as e:  # noqa: BLE001
        raise MetadataToolError(ErrorClass.CORRUPT, f"pikepdf failed to open: {e}") from e


def _objgen(obj):
    return getattr(obj, "objgen", None)


def _collect_manifest_objs(pdf) -> list:
    """Every indirect object that IS a C2PA manifest store (not a filespec
    pointing at one). Same predicate fmt_c2pa.detect_pdf_c2pa uses.
    """
    import pikepdf

    out = []
    for obj in pdf.objects:
        try:
            if not isinstance(obj, (pikepdf.Dictionary, pikepdf.Stream)):
                continue
            if "/AFRelationship" in obj and str(obj.get("/AFRelationship")) == "/C2PA_Manifest":
                out.append(obj)
                continue
            subtype = obj.get("/Subtype") if "/Subtype" in obj else None
            if subtype is not None and "c2pa" in str(subtype).lower():
                out.append(obj)
        except Exception:  # noqa: BLE001
            continue
    return out


def _is_c2pa_filespec(entry, manifest_ids: set) -> bool:
    """True only for a /AF or /EmbeddedFiles entry that is (or embeds) a C2PA
    manifest. Everything else — a Factur-X/ZUGFeRD invoice XML, a user's
    attached spreadsheet — is somebody's actual document content and must
    survive the safe tier untouched.
    """
    try:
        if _objgen(entry) is not None and _objgen(entry) in manifest_ids:
            return True
        if "/AFRelationship" in entry and str(entry.get("/AFRelationship")) == "/C2PA_Manifest":
            return True
        subtype = entry.get("/Subtype") if "/Subtype" in entry else None
        if subtype is not None and "c2pa" in str(subtype).lower():
            return True
        ef = entry.get("/EF") if "/EF" in entry else None
        if ef is not None:
            for key in ("/F", "/UF", "/DOS", "/Mac", "/Unix"):
                if key in ef:
                    stream = ef.get(key)
                    if _objgen(stream) is not None and _objgen(stream) in manifest_ids:
                        return True
                    st = stream.get("/Subtype") if hasattr(stream, "get") and "/Subtype" in stream else None
                    if st is not None and "c2pa" in str(st).lower():
                        return True
    except Exception:  # noqa: BLE001
        return False
    return False


def _iter_name_tree_pairs(node, _depth: int = 0):
    """Yield (name, value) leaf pairs of a PDF name tree (/Names + /Kids)."""
    if node is None or _depth > 32:
        return
    try:
        if "/Names" in node:
            arr = node["/Names"]
            for i in range(0, len(arr) - 1, 2):
                yield arr[i], arr[i + 1]
        if "/Kids" in node:
            for kid in node["/Kids"]:
                yield from _iter_name_tree_pairs(kid, _depth + 1)
    except Exception:  # noqa: BLE001
        return


def _prune_name_tree(node, predicate, _depth: int = 0) -> bool:
    """Remove leaf pairs matching `predicate` from a name tree IN PLACE,
    keeping the tree well-formed: /Names stays a flat [key, value, ...] array,
    emptied /Kids are dropped, and /Limits is recomputed from what survives.
    Returns True if the subtree still holds any entry.
    """
    import pikepdf

    if node is None or _depth > 32:
        return True
    non_empty = False
    try:
        if "/Names" in node:
            arr = node["/Names"]
            kept = []
            for i in range(0, len(arr) - 1, 2):
                if predicate(arr[i + 1]):
                    continue
                kept.extend([arr[i], arr[i + 1]])
            if len(kept) != len(arr):
                node["/Names"] = pikepdf.Array(kept)
            non_empty = non_empty or bool(kept)
        if "/Kids" in node:
            surviving = []
            for kid in node["/Kids"]:
                if _prune_name_tree(kid, predicate, _depth + 1):
                    surviving.append(kid)
            if len(surviving) != len(node["/Kids"]):
                node["/Kids"] = pikepdf.Array(surviving)
            non_empty = non_empty or bool(surviving)
        if _depth > 0 and "/Limits" in node:
            keys = [k for k, _v in _iter_name_tree_pairs(node)]
            if keys:
                node["/Limits"] = pikepdf.Array([min(keys), max(keys)])
            else:
                del node["/Limits"]
    except Exception:  # noqa: BLE001
        return True
    return non_empty


def _is_signed(pdf) -> bool:
    try:
        acro = pdf.Root.get("/AcroForm")
        if acro is None:
            return False
        sig_flags = int(acro.get("/SigFlags", 0))
        return bool(sig_flags & 1)
    except Exception:  # noqa: BLE001
        return False


def inspect(path, raw: bytes) -> list[Finding]:
    from . import fmt_c2pa

    path_str = str(path)
    findings: list[Finding] = []

    try:
        pdf = _open(raw)
    except MetadataToolError as e:
        return [
            Finding(
                path=path_str,
                format="pdf",
                location="<document>",
                field="engine_error",
                tier="safe",
                severity="high",
                removable=False,
                note=f"{e.error_class.label}: {e.message}",
                error_class=e.error_class,
            )
        ]

    with pdf:
        if pdf.docinfo is not None and len(pdf.docinfo) > 0:
            findings.append(
                Finding(path_str, "pdf", "/Info", "document_info", "safe", "notice", True, f"{len(pdf.docinfo)} key(s)")
            )
        if "/Metadata" in pdf.Root:
            findings.append(Finding(path_str, "pdf", "/Root/Metadata", "xmp", "safe", "notice", True, ""))
        if "/PieceInfo" in pdf.Root:
            findings.append(Finding(path_str, "pdf", "/Root/PieceInfo", "piece_info", "safe", "notice", True, ""))

        page_meta = sum(1 for p in pdf.pages if "/Metadata" in p)
        if page_meta:
            findings.append(Finding(path_str, "pdf", "page/Metadata", "xmp", "safe", "notice", True, f"{page_meta} page(s)"))
        page_piece = sum(1 for p in pdf.pages if "/PieceInfo" in p)
        if page_piece:
            findings.append(Finding(path_str, "pdf", "page/PieceInfo", "piece_info", "safe", "notice", True, f"{page_piece} page(s)"))

        annot_authors = 0
        for p in pdf.pages:
            for annot in p.get("/Annots", []):
                if "/T" in annot:
                    annot_authors += 1
        if annot_authors:
            findings.append(Finding(path_str, "pdf", "annot/T", "author_name", "safe", "notice", True, f"{annot_authors} annotation(s)"))

        findings += fmt_c2pa.detect_pdf_c2pa(path_str, pdf)

        # Embedded file attachments that are NOT C2PA manifests are real
        # document content (Factur-X/ZUGFeRD invoice XML, user attachments).
        # Reported so they show up in `left_in_place`, and deliberately
        # removable=False: making them a removable safe-tier finding would
        # just reintroduce the destructive behaviour one layer down.
        try:
            manifest_ids = {g for g in (_objgen(o) for o in _collect_manifest_objs(pdf)) if g is not None}
            other = 0
            seen = set()
            for entry in pdf.Root.get("/AF", []) or []:
                key = _objgen(entry) or ("af", other)
                if key in seen or _is_c2pa_filespec(entry, manifest_ids):
                    continue
                seen.add(key)
                other += 1
            names_obj = pdf.Root.get("/Names")
            if names_obj is not None and "/EmbeddedFiles" in names_obj:
                for _name, entry in _iter_name_tree_pairs(names_obj["/EmbeddedFiles"]):
                    key = _objgen(entry) or ("ef", other)
                    if key in seen or _is_c2pa_filespec(entry, manifest_ids):
                        continue
                    seen.add(key)
                    other += 1
            if other:
                findings.append(
                    Finding(
                        path_str, "pdf", "/Names/EmbeddedFiles+/AF", "embedded_file_attachment",
                        "safe", "notice", False,
                        f"{other} non-C2PA embedded attachment(s) — preserved, never removed by this tool",
                    )
                )
        except Exception:  # noqa: BLE001
            pass

        try:
            if "/Metadata" in pdf.Root:
                xmp_bytes = bytes(pdf.Root.Metadata.read_bytes())
                findings += fmt_c2pa.detect_xmp_provenance(path_str, "pdf", xmp_bytes)
        except Exception:  # noqa: BLE001
            pass

        acro = pdf.Root.get("/AcroForm")
        if acro is not None and "/Fields" in acro and len(acro["/Fields"]) > 0:
            findings.append(Finding(path_str, "pdf", "/Root/AcroForm/Fields", "form_values", "all", "info", True, f"{len(acro['/Fields'])} field(s)"))
        names = pdf.Root.get("/Names")
        if names is not None and "/JavaScript" in names:
            findings.append(Finding(path_str, "pdf", "/Root/Names/JavaScript", "javascript", "all", "info", True, ""))
        if "/OutputIntents" in pdf.Root:
            findings.append(Finding(path_str, "pdf", "/Root/OutputIntents", "output_intents", "all", "info", True, ""))
        if "/ID" in pdf.trailer:
            # removable=False on purpose: pikepdf regenerates /ID on save, so
            # the previous `del pdf.trailer.ID` + removable=True combination
            # recorded a removal in the audit log that never actually stuck.
            findings.append(
                Finding(
                    path_str, "pdf", "trailer/ID", "trailer_id", "all", "info", False,
                    "regenerated by the PDF writer on save — cannot be removed, only replaced",
                )
            )
        if _is_signed(pdf):
            findings.append(
                Finding(
                    path_str, "pdf", "/Root/AcroForm", "digital_signature", "all", "high", True,
                    "document is digitally signed — removal (--all --yes only) invalidates the signature",
                )
            )

    return findings


def remove(raw: bytes, *, all_tier: bool) -> bytes:

    # Open (and classify encrypted/corrupt via _open's PasswordError handling)
    # BEFORE the recovery check — _requires_recovery's bare except would
    # otherwise misclassify a password-protected PDF as merely "corrupt".
    pdf = _open(raw)
    with pdf:
        if _requires_recovery(raw) and not all_tier:
            raise MetadataToolError(
                ErrorClass.CORRUPT,
                "input required structural recovery; re-run with --all --yes to accept a rebuilt document",
            )

        if _is_signed(pdf) and not all_tier:
            raise MetadataToolError(
                ErrorClass.ENCRYPTED_OR_SIGNED,
                "document is digitally signed; removal requires --all --yes and invalidates the signature",
            )

        try:
            del pdf.docinfo
        except (KeyError, AttributeError):
            pass
        if "/Metadata" in pdf.Root:
            del pdf.Root.Metadata
        if "/PieceInfo" in pdf.Root:
            del pdf.Root.PieceInfo
        for p in pdf.pages:
            if "/Metadata" in p:
                del p.Metadata
            if "/PieceInfo" in p:
                del p.PieceInfo
            for annot in p.get("/Annots", []):
                if "/T" in annot:
                    del annot.T

        import pikepdf

        manifest_objs = _collect_manifest_objs(pdf)
        manifest_ids = {g for g in (_objgen(o) for o in manifest_objs) if g is not None}

        # Prune /AF and the /Names/EmbeddedFiles name tree SURGICALLY, and
        # BEFORE the manifest objects are gutted below (once their keys are
        # gone they are no longer identifiable as manifests). A blanket
        # `del pdf.Root.AF` / `del names.EmbeddedFiles` destroyed every
        # embedded attachment — e.g. a Factur-X invoice's XML — with no
        # finding reported and no tier gate.
        def _matches(entry) -> bool:
            return _is_c2pa_filespec(entry, manifest_ids)

        if "/AF" in pdf.Root:
            try:
                kept = [e for e in pdf.Root.AF if not _matches(e)]
                if not kept:
                    del pdf.Root.AF
                elif len(kept) != len(pdf.Root.AF):
                    pdf.Root.AF = pikepdf.Array(kept)
            except Exception:  # noqa: BLE001
                pass
        names = pdf.Root.get("/Names")
        if names is not None and "/EmbeddedFiles" in names:
            try:
                tree = names["/EmbeddedFiles"]
                if not _prune_name_tree(tree, _matches):
                    del names["/EmbeddedFiles"]
            except Exception:  # noqa: BLE001
                pass

        # Clear the object's own dict keys (and stream payload, if any) in
        # place rather than reassigning the object table — dangling
        # references left pointing at it then just resolve to an empty
        # dict/stream instead of the manifest content.
        for obj in manifest_objs:
            try:
                is_stream = isinstance(obj, pikepdf.Stream)
                for k in list(obj.keys()):
                    del obj[k]
                if is_stream:
                    obj.write(b"")
            except Exception:  # noqa: BLE001
                continue

        if all_tier:
            acro = pdf.Root.get("/AcroForm")
            if acro is not None and "/Fields" in acro:
                del acro.Fields
            names = pdf.Root.get("/Names")
            if names is not None and "/JavaScript" in names:
                del names.JavaScript
            if "/OutputIntents" in pdf.Root:
                del pdf.Root.OutputIntents
            # trailer /ID deliberately left alone — pdf.save() regenerates it
            # regardless, so deleting it only produced a false audit claim.

        buf = io.BytesIO()
        pdf.save(buf)
        return buf.getvalue()
