#!/usr/bin/env python3
"""Secret store client stub for human_pending_tasks.secret_ref.

human_pending_tasks NEVER holds a credential/cookie value in the clear — only
a pointer (secret_ref). This module is the single place that resolves that
pointer to a value. Backend TBD (see jarvis-control3/architecture/08-allowlist-and-secrets.md
and config/env.md) — for now this is a stub that only supports env-var-backed
refs, sufficient for the two real call-sites wired in this session.
"""
from __future__ import annotations

import os


def resolve(secret_ref: str | None) -> str | None:
    """Resolve a secret_ref to its value. Returns None if unset or unresolved.

    Convention: secret_ref of the form "env:VAR_NAME" resolves from the
    process environment. Any other form is unsupported today and resolves
    to None rather than guessing.
    """
    if not secret_ref:
        return None
    if secret_ref.startswith("env:"):
        return os.environ.get(secret_ref[len("env:"):]) or None
    return None
