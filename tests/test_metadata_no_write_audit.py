"""Mechanically enforces the standing rule that metadata_audit.py can never
write: removal is always a human decision (metadata_remove.py --apply),
never something a read-only audit pass can trigger — see
bin/tools/metadata_audit.py's own docstring and the plan this implements.

AST-walks the module source rather than importing and calling it, so this
test catches a write path reachable through *any* call chain, not just the
ones exercised by other tests.
"""

import ast
from pathlib import Path

AUDIT_PATH = Path(__file__).resolve().parent.parent / "bin" / "tools" / "metadata_audit.py"
LIB_DIR = Path(__file__).resolve().parent.parent / "bin" / "tools" / "metadata_lib"

# safeio.py itself is a mixed module (iter_files() is a read-only directory
# walker the audit CLI legitimately uses); what's forbidden is importing or
# calling its actual write-capable members specifically.
FORBIDDEN_NAME_PREFIXES = ("remove_", "clean_")
FORBIDDEN_WRITE_SYMBOLS = ("atomic_replace", "make_tempdir_same_fs", "write_new_file")


def _write_capable_symbols() -> set[str]:
    """Every write-capable function metadata_lib actually defines today.

    Matching on the `remove_`/`clean_` prefixes alone missed the byte-mutating
    entry points that are simply called `remove` (fmt_pdf.remove,
    fmt_image.remove, fmt_ooxml.remove) — i.e. the guard did not cover the
    functions most likely to be wired into the audit path by mistake.
    """
    symbols = set(FORBIDDEN_WRITE_SYMBOLS)
    sources = list(LIB_DIR.glob("fmt_*.py")) + [LIB_DIR / "safeio.py"]
    for src in sorted(sources):
        if not src.exists():
            continue
        for node in ast.walk(_load_tree(src)):
            if isinstance(node, ast.FunctionDef) and (
                node.name == "remove"
                or node.name.startswith(FORBIDDEN_NAME_PREFIXES)
                or node.name in FORBIDDEN_WRITE_SYMBOLS
            ):
                symbols.add(node.name)
    return symbols


def _load_tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(), filename=str(path))


def _all_names_and_attrs(tree: ast.Module):
    names = []
    attrs = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.append(node.id)
        elif isinstance(node, ast.Attribute):
            attrs.append(node.attr)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.append(alias.asname or alias.name)
                if isinstance(node, ast.ImportFrom) and node.module:
                    names.append(node.module)
    return names, attrs


def test_metadata_audit_imports_no_write_capable_symbol():
    tree = _load_tree(AUDIT_PATH)
    names, attrs = _all_names_and_attrs(tree)
    forbidden = _write_capable_symbols()

    for n in names:
        assert n not in forbidden, f"metadata_audit.py imports a write-capable symbol: {n}"
        for prefix in FORBIDDEN_NAME_PREFIXES:
            assert not n.startswith(prefix), f"metadata_audit.py references a write-capable symbol: {n}"

    for a in attrs:
        assert a not in forbidden, f"metadata_audit.py calls a write-capable attribute: {a}"
        for prefix in FORBIDDEN_NAME_PREFIXES:
            assert not a.startswith(prefix), f"metadata_audit.py calls a write-capable attribute: {a}"


def test_guard_actually_covers_the_bare_remove_entry_points():
    """The guard set is derived, so assert it really contains the functions the
    prefix-only version silently ignored.
    """
    forbidden = _write_capable_symbols()
    assert "remove" in forbidden
    assert "write_new_file" in forbidden
    assert "atomic_replace" in forbidden


def test_metadata_audit_source_has_no_apply_flag():
    """No --apply/--yes CLI flag is registered, and the module never calls
    os.replace/atomic_replace — checked as actual calls/args, not prose
    substrings, since the help text legitimately tells the user to go run
    metadata_remove.py --apply.
    """
    tree = _load_tree(AUDIT_PATH)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "add_argument":
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        assert arg.value not in ("--apply", "--yes"), (
                            f"metadata_audit.py must not register a {arg.value} flag"
                        )
            if isinstance(func, ast.Attribute) and func.attr == "replace":
                assert not (
                    isinstance(func.value, ast.Name) and func.value.id == "os"
                ), "metadata_audit.py must never call os.replace"

    names, attrs = _all_names_and_attrs(tree)
    assert "atomic_replace" not in names
    assert "atomic_replace" not in attrs


def test_no_fmt_module_remove_function_is_imported_by_audit():
    """Belt-and-suspenders: even a `from metadata_lib.fmt_pdf import *` or a
    dynamically-built attribute access would be caught by name/attr scan
    above; this additionally asserts every fmt_*.py remove_*/clean_* function
    name that exists today is absent from the audit module's raw source.
    """
    forbidden_symbols = set()
    for fmt_file in sorted(LIB_DIR.glob("fmt_*.py")):
        tree = _load_tree(fmt_file)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and (
                node.name.startswith("remove_") or node.name.startswith("clean_")
            ):
                forbidden_symbols.add(node.name)

    source = AUDIT_PATH.read_text()
    for sym in forbidden_symbols:
        assert sym not in source, f"metadata_audit.py source contains write-capable symbol name: {sym}"
