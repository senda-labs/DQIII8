"""
tests/test_dependency_manifests.py — requirements.txt / pyproject.toml drift guard.

Stage 2 (2026-08-12): the two manifests had silently diverged (langgraph, agno,
typing_extensions missing from pyproject.toml; pytest miscategorized as "Core" in
requirements.txt). This test parses both and asserts every non-dev runtime package
declared in one also appears in the other, so that drift can't silently reopen.
"""

import re
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python <3.11
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "requirements.txt"
PYPROJECT = ROOT / "pyproject.toml"

# packages that are dev-only tooling, not runtime dependencies — excluded from
# the cross-manifest comparison on both sides.
DEV_ONLY = {"pytest", "ruff", "mypy", "pip-tools"}

_REQ_LINE_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(.*)$")


def _normalize(name: str) -> str:
    return name.lower().replace("_", "-")


def _parse_requirements_txt() -> dict[str, str]:
    pkgs: dict[str, str] = {}
    for line in REQUIREMENTS.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _REQ_LINE_RE.match(line)
        if not m:
            continue
        name, spec = m.group(1), m.group(2)
        pkgs[_normalize(name)] = spec
    return pkgs


def _parse_pyproject_toml() -> tuple[dict[str, str], dict[str, str]]:
    data = tomllib.loads(PYPROJECT.read_text())
    runtime: dict[str, str] = {}
    for entry in data["project"]["dependencies"]:
        m = _REQ_LINE_RE.match(entry.strip())
        if m:
            runtime[_normalize(m.group(1))] = m.group(2)
    dev: dict[str, str] = {}
    for entry in data["project"]["optional-dependencies"].get("dev", []):
        m = _REQ_LINE_RE.match(entry.strip())
        if m:
            dev[_normalize(m.group(1))] = m.group(2)
    return runtime, dev


def test_requirements_txt_runtime_packages_declared_in_pyproject():
    req = _parse_requirements_txt()
    pyproject_runtime, pyproject_dev = _parse_pyproject_toml()
    known = set(pyproject_runtime) | set(pyproject_dev) | DEV_ONLY
    missing = [name for name in req if name not in DEV_ONLY and name not in known]
    assert (
        not missing
    ), f"requirements.txt declares runtime package(s) not in pyproject.toml: {missing}"


def test_pyproject_runtime_packages_declared_in_requirements_txt():
    req = _parse_requirements_txt()
    pyproject_runtime, _pyproject_dev = _parse_pyproject_toml()
    missing = [name for name in pyproject_runtime if name not in req]
    assert (
        not missing
    ), f"pyproject.toml declares runtime package(s) not in requirements.txt: {missing}"


def test_pytest_is_not_declared_under_requirements_txt_core_section():
    lines = REQUIREMENTS.read_text().splitlines()
    core_start = next(
        i for i, line in enumerate(lines) if line.strip() == "# Core (used by most scripts)"
    )
    core_end = next(
        i
        for i, line in enumerate(lines[core_start + 1 :], start=core_start + 1)
        if not line.strip() or line.startswith("#")
    )
    core_block = lines[core_start:core_end]
    assert not any(
        line.lower().startswith("pytest") for line in core_block
    ), "pytest is dev-only tooling; should not be under requirements.txt's Core section"


def test_sqlite_vec_exact_pinned_in_both_manifests():
    req = _parse_requirements_txt()
    pyproject_runtime, _ = _parse_pyproject_toml()
    assert req["sqlite-vec"].startswith(
        "=="
    ), f"requirements.txt sqlite-vec should be exact-pinned, got: {req['sqlite-vec']}"
    assert pyproject_runtime["sqlite-vec"].startswith(
        "=="
    ), f"pyproject.toml sqlite-vec should be exact-pinned, got: {pyproject_runtime['sqlite-vec']}"


if __name__ == "__main__":
    sys.exit(__import__("pytest").main([__file__, "-v"]))
