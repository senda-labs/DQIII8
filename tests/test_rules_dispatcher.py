"""Tests for rules_dispatcher.py — registry reachability, token budget, fail-open.

Written 2026-08-17 (audit gap 6) against the ALREADY-CORRECTED dispatcher
(remediation groups A-E applied), so the pre-fix bugs are never fossilised as
expected behaviour.

Two invariants this file exists to protect:
  1. Every alias in `_REGISTRY` is reachable by some real tool call AND points
     at a file that exists (the `routing.md` / `performance.md` class of bug,
     in both directions).
  2. The token budget quoted in the dispatcher docstring, `DYNAMIC.md` and
     `02_hooks_and_permissions.md` matches what `token_estimate()` actually
     returns today.
"""

import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).parent.parent / ".claude" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import rules_dispatcher as rd  # noqa: E402
import rules_registry_introspect as intro  # noqa: E402

DISPATCHER_SRC = HOOKS_DIR / "rules_dispatcher.py"


# ── Reachability ────────────────────────────────────────────────────────────
# The five-source reachability logic (four declarative tables + the hardcoded
# path substrings inside get_rules(), recovered from the AST) lives in
# .claude/hooks/rules_registry_introspect.py so that this test file and the
# pre-commit gate bin/tools/validate_rules_registry.py cannot drift apart.
# A naive four-table union would report `hooks-perms`, `tiering` and
# `db-mutations` as orphans — they are wired to Edit/Write path substrings
# (".claude/hooks", "openrouter_wrapper", "database/"), not to any table.


def declarative_aliases() -> set[str]:
    return intro.declarative_aliases(rd)


def inline_aliases() -> set[str]:
    return intro.inline_aliases(
        DISPATCHER_SRC.read_text(encoding="utf-8"), rd._REGISTRY
    )


def reachable_aliases() -> set[str]:
    return declarative_aliases() | inline_aliases()


# The orphan set is now EMPTY and must stay that way. `git-workflow`, `workflow`
# and `testing` (reported 2026-08-17, group F) were resolved by deleting the alias
# + file: all three were generic boilerplate already superseded by wired DQIII8
# rules (python.md § Testing, git-safety.md, 02_hooks_and_permissions.md), and each
# cited a non-existent agent or file. The unique DQIII8 line from git-workflow.md
# (the commit attribution trailer) was merged into git-safety.md first.
KNOWN_ORPHANS: set[str] = set()


def test_core_behavior_always_injected():
    """`core-behavior` is in _ALWAYS and resolves to a real, readable file."""
    assert "core-behavior" in rd._ALWAYS
    path = (rd.RULES_DB / rd._REGISTRY["core-behavior"]).resolve()
    assert path.is_file(), f"core-behavior alias points at missing file: {path}"
    assert path.read_text(encoding="utf-8").strip(), "core-behavior file is empty"
    # And it actually lands in the injected block for an arbitrary tool call.
    injected = rd.get_rules("Glob", {})
    assert "Core Behavior" in injected


def test_every_registry_alias_is_reachable():
    """No alias in _REGISTRY may be unreachable from any tool call."""
    orphans = set(rd._REGISTRY) - reachable_aliases()
    assert not orphans, f"orphaned aliases in _REGISTRY: {sorted(orphans)}"


def test_no_new_orphan_aliases():
    """Regression guard: no NEW orphan may appear (KNOWN_ORPHANS is empty today)."""
    orphans = set(rd._REGISTRY) - reachable_aliases()
    new = orphans - KNOWN_ORPHANS
    assert not new, f"NEW orphaned aliases introduced: {sorted(new)}"


def test_no_reachable_alias_is_unregistered():
    """Every alias referenced by a mapping table must exist in _REGISTRY.

    The other direction of the same drift: get_rules() silently drops aliases
    that are not in _REGISTRY, so a typo in a mapping is invisible at runtime.
    """
    dangling = reachable_aliases() - set(rd._REGISTRY)
    assert not dangling, f"mappings reference unregistered aliases: {sorted(dangling)}"


def test_governance_and_agent_aliases_all_resolve():
    """Every _REGISTRY alias — reachable or not — points at an existing file."""
    missing = {
        alias: str((rd.RULES_DB / rel).resolve())
        for alias, rel in rd._REGISTRY.items()
        if not (rd.RULES_DB / rel).is_file()
    }
    assert not missing, f"_REGISTRY aliases with missing files: {missing}"


# ── Token budget ────────────────────────────────────────────────────────────

# Measured 2026-08-17 with token_estimate() over the representative matrix below,
# after remediation groups A-F *and* the group-F residual sweep (orphan alias purge
# + the git-safety.md merge). Re-measure and update the dispatcher docstring,
# DYNAMIC.md and 02_hooks_and_permissions.md together whenever an _ALWAYS or
# heavily-triggered rule file changes size, or a trigger is added/removed — this
# range went stale twice on 2026-08-17 alone.
MEASURED_FLOOR = 1432   # _ALWAYS only (ops + core-behavior)
MEASURED_CEILING = 4469  # Bash matching agent|orchestrat → +tiering+agents+plan-gate
TOLERANCE = 0.05

# tool, tool_input, expected label
BUDGET_MATRIX = [
    ("Bash", {"command": "ls"}, "bash-no-keyword"),
    # NB: keep this command free of other trigger words ("cc", "python3", …) —
    # it is the single-trigger ceiling case, not a combined worst case.
    ("Bash", {"command": "dq agent orchestrator status"}, "bash-agent-keyword"),
    ("Bash", {"command": "git status"}, "bash-git"),
    ("Bash", {"command": "python3 script.py"}, "bash-python"),
    ("Bash", {"command": "sqlite3 database/dqiii8.db '.tables'"}, "bash-sqlite3"),
    ("Bash", {"command": "tmux ls"}, "bash-workspace"),
    ("Bash", {"command": "firecrawl scrape https://x"}, "bash-web"),
    ("Edit", {"file_path": "/root/dqiii8/README.md"}, "edit-md"),
    ("Edit", {"file_path": "/root/dqiii8/bin/core/foo.py"}, "edit-py"),
    ("Edit", {"file_path": "/root/dqiii8/.claude/hooks/foo.py"}, "edit-hook-py"),
    ("Write", {"file_path": "/root/dqiii8/database/schema_v2.sql"}, "write-sql"),
    ("Read", {"file_path": "/root/dqiii8/README.md"}, "read"),
    ("Agent", {}, "agent-tool"),
    ("WebFetch", {"url": "https://example.com"}, "webfetch"),
    ("Glob", {}, "glob"),
    ("Grep", {}, "grep"),
    ("TodoWrite", {}, "todowrite"),
]


@pytest.mark.parametrize("tool,tool_input,label", BUDGET_MATRIX)
def test_token_budget_matrix(tool, tool_input, label):
    """Every representative call sits inside the documented token range."""
    tokens = rd.token_estimate(rd.get_rules(tool, tool_input))
    assert tokens >= MEASURED_FLOOR * (1 - TOLERANCE), (
        f"{label}: {tokens} tokens is below the documented floor "
        f"{MEASURED_FLOOR} — is core-behavior/ops still in _ALWAYS?"
    )
    assert tokens <= MEASURED_CEILING * (1 + TOLERANCE), (
        f"{label}: {tokens} tokens exceeds the documented ceiling "
        f"{MEASURED_CEILING} — re-measure and update the docstring, DYNAMIC.md "
        f"and 02_hooks_and_permissions.md."
    )


def test_token_budget_floor_is_always_set_only():
    """The floor case injects exactly _ALWAYS and nothing else."""
    bare = rd.get_rules("Glob", {})
    assert rd.token_estimate(bare) == min(
        rd.token_estimate(rd.get_rules(t, i)) for t, i, _ in BUDGET_MATRIX
    )
    assert abs(rd.token_estimate(bare) - MEASURED_FLOOR) <= MEASURED_FLOOR * TOLERANCE


def test_token_budget_ceiling_case_is_the_max():
    """The agent/orchestrat Bash trigger remains the most expensive case."""
    worst = max(
        (rd.token_estimate(rd.get_rules(t, i)), lbl) for t, i, lbl in BUDGET_MATRIX
    )
    assert worst[1] in ("bash-agent-keyword", "agent-tool")


# ── Fail-open ───────────────────────────────────────────────────────────────


def test_unreadable_rule_file_fails_open(monkeypatch, capsys):
    """A missing rule file degrades to "" + stderr warning, never an exception."""
    monkeypatch.setitem(rd._REGISTRY, "ops", "does-not-exist-xyz.md")
    assert rd._read("ops") == ""
    err = capsys.readouterr().err
    assert "rules_dispatcher" in err and "unreadable" in err


def test_unknown_alias_fails_open(capsys):
    """An alias missing from _REGISTRY warns instead of raising KeyError."""
    assert rd._read("no-such-alias") == ""
    assert "unknown rule alias" in capsys.readouterr().err


def test_get_rules_survives_unreadable_file(monkeypatch, capsys):
    """A broken rule file must not take down the whole injection block."""
    monkeypatch.setitem(rd._REGISTRY, "core-behavior", "gone.md")
    out = rd.get_rules("Bash", {"command": "git status"})
    assert "rules_dispatcher" in capsys.readouterr().err
    assert out, "dispatcher returned nothing instead of the surviving rules"
    assert "Core Behavior" not in out
    assert "[DQIII8 Rules" in out


def test_get_rules_all_files_broken_returns_empty(monkeypatch):
    """If every file is unreadable, return "" rather than a bare header."""
    monkeypatch.setattr(rd, "_REGISTRY", {k: "gone.md" for k in rd._REGISTRY})
    assert rd.get_rules("Bash", {"command": "ls"}) == ""


def test_unknown_tool_returns_always_set():
    """An unmapped tool still gets the _ALWAYS rules and does not raise."""
    out = rd.get_rules("SomeFutureTool", {})
    assert rd.token_estimate(out) >= MEASURED_FLOOR * (1 - TOLERANCE)
