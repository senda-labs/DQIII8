#!/usr/bin/env python3
"""Shared introspection of `rules_dispatcher._REGISTRY` reachability.

Single source of truth for the question "which aliases can a real tool call
actually reach?", imported by BOTH:

  * ``tests/test_rules_dispatcher.py``   (unit-test invariant)
  * ``bin/tools/validate_rules_registry.py`` (pre-commit gate)

Why this module exists instead of a two-line set union in each caller:
reachability has **five** sources, not four. Four are declarative tables
(``_ALWAYS``, ``_TOOL_RULES``, ``_BASH_KEYWORD_RULES``, ``_EXT_RULES``); the
fifth is a set of hardcoded path substrings *inside* ``get_rules()`` itself::

    if ".claude/hooks" in path:            aliases.extend(["hooks-perms"])
    if "openrouter_wrapper" in path ...:   aliases.extend(["tiering"])
    if "database/" in path ...:            aliases.extend(["db-mutations"])

A naive four-table union therefore reports ``hooks-perms``, ``tiering`` and
``db-mutations`` as orphans — a false positive that would have been "fixed" by
deleting three live, correctly-wired aliases. The fifth source is recovered
from the AST of ``get_rules()`` rather than hardcoded, so a future inline alias
is picked up automatically.

Every function takes the dispatcher **module object** plus its **source text**,
so callers can introspect either the live worktree module (tests) or a module
reconstructed from staged git-index content (pre-commit validator).
"""

from __future__ import annotations

import ast
import importlib.util
from types import ModuleType

__all__ = [
    "load_dispatcher",
    "declarative_aliases",
    "inline_aliases",
    "reachable_aliases",
    "orphan_aliases",
    "dangling_aliases",
]


def load_dispatcher(source: str, name: str = "rules_dispatcher_snapshot") -> ModuleType:
    """Materialise a dispatcher module from arbitrary source text.

    Used by the pre-commit validator to introspect the *staged* dispatcher
    rather than whatever happens to be sitting in the worktree. Importing by
    execution (instead of re-parsing the tables out of the AST) is deliberate:
    the tables are then the exact objects ``get_rules()`` would use, so this
    check can never disagree with runtime for parsing reasons.

    ``rules_dispatcher`` has no import-time side effects — it binds constants
    and compiles regexes, touching neither the filesystem nor the network.
    """
    spec = importlib.util.spec_from_loader(name, loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__file__ = f"<{name}>"
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


def declarative_aliases(module: ModuleType) -> set[str]:
    """Aliases reachable through the four declarative mapping tables."""
    aliases: set[str] = set(module._ALWAYS)
    for rule_list in module._TOOL_RULES.values():
        aliases.update(rule_list)
    for _pattern, rule_list in module._BASH_KEYWORD_RULES:
        aliases.update(rule_list)
    for rule_list in module._EXT_RULES.values():
        aliases.update(rule_list)
    return aliases


def inline_aliases(source: str, registry: dict[str, str]) -> set[str]:
    """Aliases injected by the hardcoded path branches inside ``get_rules()``.

    Any string constant appearing anywhere in ``get_rules()`` that is also a
    registry key counts as reachable. Over-inclusive by design: a false
    *negative* here silently deletes a wired alias, a false positive merely
    keeps an alias one extra release.
    """
    tree = ast.parse(source)
    fn = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "get_rules"
        ),
        None,
    )
    if fn is None:  # pragma: no cover - dispatcher without get_rules is a bigger problem
        return set()
    return {
        n.value
        for n in ast.walk(fn)
        if isinstance(n, ast.Constant)
        and isinstance(n.value, str)
        and n.value in registry
    }


def reachable_aliases(module: ModuleType, source: str) -> set[str]:
    """Union of all five reachability sources."""
    return declarative_aliases(module) | inline_aliases(source, module._REGISTRY)


def orphan_aliases(module: ModuleType, source: str) -> set[str]:
    """Registered but unreachable — dead weight nothing can ever inject."""
    return set(module._REGISTRY) - reachable_aliases(module, source)


def dangling_aliases(module: ModuleType, source: str) -> set[str]:
    """Referenced by a mapping but absent from ``_REGISTRY``.

    The other direction of the same drift: ``get_rules()`` silently drops
    aliases missing from ``_REGISTRY``, so a typo in a mapping table is
    invisible at runtime.
    """
    return reachable_aliases(module, source) - set(module._REGISTRY)
