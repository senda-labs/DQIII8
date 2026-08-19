#!/usr/bin/env python3
"""Shared agent_actions writer helpers (Stage 3).

Not a new abstraction over the INSERT/UPDATE statements themselves — those stay
in each of the 5 write sites (pre_tool_use.py's open, post_tool_use.py's
close-out, post_tool_use_failure.py's failure UPDATE, openrouter_wrapper.py's
single-shot log_to_db, dqiii8_bot.py's `_log_cc_command`) because their
matching/close semantics differ too much to unify safely. What was genuinely
duplicated across sites is centralized here: project resolution's fail-open
try/except, and request_id generation for a fallback cascade.
"""

from __future__ import annotations

import logging
import uuid

log = logging.getLogger(__name__)


def resolve_project_safe(session_id: str, cwd: str | None = None) -> str | None:
    """Best-effort project_context SSOT lookup. Fails open to None — a hook or
    wrapper must never abort an action because project resolution broke."""
    try:
        from core.project_context import resolve_project

        return resolve_project(session_id=session_id, cwd=cwd) if cwd is not None else resolve_project(session_id=session_id)
    except Exception as e:
        log.debug("action_log: resolve_project failed (best-effort): %s", e)
        return None


def generate_request_id() -> str:
    """One request_id per logical call, reused across every fallback attempt
    in a provider cascade so they can be grouped in agent_actions afterward."""
    return uuid.uuid4().hex[:16]
