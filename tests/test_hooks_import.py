"""Every hook must at least parse, and the library hooks must import cleanly.

Why this exists: on 2026-08-20 a patch added a `Sequence[str] | None` annotation
to permission_analyzer.py without the matching import. The module raised
NameError at import time, pre_tool_use.py failed closed, and EVERY tool call was
denied until a human restored the file by hand. Nothing in the suite noticed,
because nothing in the suite imported the hooks.

Ceiling, stated rather than implied: this does NOT execute the script-style
hooks. They read a JSON payload from stdin and have real side effects — stop.py
auto-commits and pushes to the `premium` remote — so running them from a test
would mutate the repo. Compile-checking catches syntax errors everywhere; the
cold-import check catches the NameError/ImportError class in exactly the two
modules that pre_tool_use.py imports at runtime.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).parent.parent / ".claude" / "hooks"
HOOK_FILES = sorted(HOOKS_DIR.glob("*.py"))

# Imported by pre_tool_use.py on every single tool call, so a broken import here
# takes the whole permission system down rather than degrading one hook.
LIBRARY_HOOKS = ["permission_analyzer", "rules_dispatcher"]


def test_hooks_directory_is_not_empty():
    """A glob that silently matches nothing would make every test below vacuous."""
    assert HOOK_FILES, f"no hooks found under {HOOKS_DIR}"


@pytest.mark.parametrize("hook", HOOK_FILES, ids=lambda p: p.name)
def test_hook_compiles(hook):
    compile(hook.read_text(encoding="utf-8"), str(hook), "exec")


@pytest.mark.parametrize("module", LIBRARY_HOOKS)
def test_library_hook_imports_in_a_cold_process(module):
    """Cold subprocess, not an in-process import.

    pytest has already imported permission_analyzer via conftest by the time
    this runs, so an in-process import would hit sys.modules and prove nothing.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys; sys.path.insert(0, {str(HOOKS_DIR)!r}); import {module}",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "ANTHROPIC_API_KEY": ""},
    )
    assert result.returncode == 0, f"{module} failed to import:\n{result.stderr}"
