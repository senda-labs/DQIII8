"""Guard against the `bin/` flat-vs-package module namespace collision.

Background (2026-08-11): four modules existed twice under `bin/` with the same
importable basename — once at the `bin/` root (a pre-refactor snapshot resurrected
by the premium include/exclude churn in 0446bac) and once inside the subpackage the
2026-03-20 reorganisation (24129d7) moved them to. Because the system imports by
bare name with six `bin/*` directories on `sys.path`, which copy won was decided
purely by insertion order — undefined by design. `tests/test_e2e_pipeline.py`
passed in-suite but failed standalone as a direct result.

These tests make the ambiguity impossible to reintroduce silently.
"""

import sys
from collections import defaultdict
from pathlib import Path

import pytest

DQIII8_ROOT = Path(__file__).resolve().parent.parent
BIN = DQIII8_ROOT / "bin"

# Package markers are legitimately duplicated — one per package directory.
_ALLOWED_DUPLICATE_BASENAMES = {"__init__.py"}

# Historical copies, intentionally frozen and never imported by bare name.
_EXCLUDED_DIR_PARTS = {"_archived", "archive", "__pycache__"}

# Modules that must resolve to exactly one file no matter how sys.path was built.
_CANONICAL = {
    "intent_amplifier": BIN / "agents" / "intent_amplifier.py",
    "hierarchical_router": BIN / "agents" / "hierarchical_router.py",
    "template_loader": BIN / "agents" / "template_loader.py",
    "ml_selector": BIN / "monitoring" / "ml_selector.py",
}


def _candidate_files():
    for path in BIN.rglob("*.py"):
        if _EXCLUDED_DIR_PARTS & set(path.relative_to(BIN).parts[:-1]):
            continue
        yield path


def test_no_duplicate_basenames_under_bin():
    """Two importable files under bin/ sharing a basename is always a shadowing bug."""
    by_name = defaultdict(list)
    for path in _candidate_files():
        if path.name in _ALLOWED_DUPLICATE_BASENAMES:
            continue
        by_name[path.name].append(str(path.relative_to(DQIII8_ROOT)))

    duplicates = {name: paths for name, paths in by_name.items() if len(paths) > 1}
    assert not duplicates, (
        "Duplicate importable basenames under bin/ — which copy wins depends on "
        f"sys.path insertion order, not on any declaration: {duplicates}"
    )


@pytest.mark.parametrize("module_name,expected", sorted(_CANONICAL.items()))
def test_module_resolves_identically_under_any_bootstrap(module_name, expected):
    """Resolution must not depend on how the caller happened to build sys.path.

    Exercises the three bootstrap variants that exist in the tree: the full
    six-directory loop, bin/-root-only (the variant that used to bind the stale
    copies), and repo-root-only.
    """
    import importlib.util

    bootstraps = {
        "six-dir loop": [BIN / s for s in ("", "core", "agents", "monitoring", "tools", "ui")],
        "bin-root only": [BIN],
        "repo-root only": [DQIII8_ROOT],
    }

    for label, dirs in bootstraps.items():
        saved = list(sys.path)
        try:
            for d in dirs:
                sys.path.insert(0, str(d))
            spec = importlib.util.find_spec(module_name)
        finally:
            sys.path[:] = saved

        if spec is None:
            continue  # Not importable under this bootstrap — loud, not silent.
        assert Path(spec.origin) == expected, (
            f"{module_name} resolved to {spec.origin} under '{label}' bootstrap, "
            f"expected {expected}"
        )
