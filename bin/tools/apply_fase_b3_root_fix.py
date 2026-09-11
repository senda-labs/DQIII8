#!/usr/bin/env python3
"""Fase B, part 3 — root-cause fix for concurrent-sibling misattribution.

The Fase B part 2 diagnostic (see /var/log/dqiii8/hooks.log, 2026-09-04 11:12)
confirmed empirically that Claude Code's real PreToolUse payload DOES carry
`agent_id` and `agent_type` for every subagent-issued tool call, correctly
scoped per subagent — two concurrent siblings never showed each other's
agent_id in the log. The old code in pre_tool_use.py received this value but
discarded it: it only used `agent_id` to decide "does this look like a raw
hex ID that needs resolving into a name", then threw it away and ran an
ambiguous LIFO lookup against agent_registry to reconstruct an agent_id that
was already sitting in the payload the whole time.

This patch uses the harness-native agent_id/agent_type directly when present
(the common case for every subagent call, confirmed empirically) and only
falls back to the old best-effort LIFO/lookup-file resolution when they are
genuinely absent (top-level session calls, or an older harness version) —
eliminating the concurrent-sibling cross-attribution bug at the root, not
just narrowing it.

Run by hand, outside any agent session. Safe to re-run.

Usage: python3 bin/tools/apply_fase_b3_root_fix.py [--hooks-dir PATH]
"""

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

OLD_BLOCK = (
    'agent = data.get("agent_id", data.get("agent_name", ""))\n'
    '_worktree = ""\n'
    "_agent_id = (\n"
    "    agent\n"
    "    if agent\n"
    "    and len(agent) == 17\n"
    '    and agent[0] == "a"\n'
    '    and all(c in "0123456789abcdef" for c in agent[1:])\n'
    '    else ""\n'
    ")\n"
    "if not agent or _agent_id:\n"
    "    # Stage 1 / Correction G: subagent_start.py's lookup file is keyed by\n"
    "    # agent_id, not session_id — resolve session_id -> agent_id via\n"
    "    # agent_registry before building the filename (mirrors post_tool_use.py's\n"
    "    # Stage 0 fix). A raw hex agent_id is not a usable agent name either, so\n"
    '    # it takes the same resolution path as the "no agent" case.\n'
    '    agent = "claude-sonnet-5"\n'
    "    try:\n"
    '        _direct = os.path.join(DQIII8_ROOT, "tmp", f"dqiii8_agent_{session}.json")\n'
    "        _lookup_path = _direct if os.path.exists(_direct) else None\n"
    "        if _lookup_path is None:\n"
    "            import sqlite3 as _rics\n"
    "\n"
    '            _reg_db = os.path.join(DQIII8_ROOT, "database", "dqiii8.db")\n'
    "            if os.path.exists(_reg_db):\n"
    "                _rconn = _rics.connect(_reg_db, timeout=2)\n"
    "                _rrow = _rconn.execute(\n"
    '                    "SELECT agent_id FROM agent_registry WHERE parent_session=? AND end_time IS NULL "\n'
    '                    "ORDER BY start_time DESC LIMIT 1",\n'
    "                    (session,),\n"
    "                ).fetchone()  # Rango 6 CEILING (narrowed, Fase B part 2): excludes siblings that already\n"
    "                # closed — still ambiguous if 2+ siblings are open at the same instant, that needs a\n"
    "                # harness-provided per-call correlator dqiii8 does not have today.\n"
    "                _rconn.close()\n"
    "                if _rrow:\n"
    "                    _agent_id = _rrow[0] or _agent_id\n"
    "                    _cand = os.path.join(\n"
    '                        DQIII8_ROOT, "tmp", f"dqiii8_agent_{_rrow[0]}.json"\n'
    "                    )\n"
    "                    if os.path.exists(_cand):\n"
    "                        _lookup_path = _cand\n"
    "        if _lookup_path:\n"
    '            with open(_lookup_path, encoding="utf-8") as _f:\n'
    "                _lookup = json.load(_f)\n"
    '                agent = _lookup.get("agent_type", "claude-sonnet-5")\n'
    '                _worktree = _lookup.get("worktree_path", "") or ""\n'
    "                if not _agent_id:\n"
    '                    _agent_id = _lookup.get("agent_id", "") or _agent_id\n'
    "    except Exception as e:\n"
    '        log.debug("pre_tool_use: agent lookup failed (best-effort): %s", e)\n'
)

NEW_BLOCK = (
    '_agent_id = data.get("agent_id", "") or ""\n'
    '_agent_type = data.get("agent_type", "") or ""\n'
    '_worktree = ""\n'
    "if _agent_id and _agent_type:\n"
    "    # Fase B part 3 (root fix, 2026-09-04): the harness DOES send agent_id/\n"
    "    # agent_type on every subagent-issued PreToolUse call, correctly scoped\n"
    "    # per subagent even under concurrent siblings — confirmed empirically via\n"
    "    # the part-2 diagnostic log, not inferred. Use it directly: no LIFO guess.\n"
    "    agent = _agent_type\n"
    "    try:\n"
    '        _direct = os.path.join(DQIII8_ROOT, "tmp", f"dqiii8_agent_{_agent_id}.json")\n'
    "        if os.path.exists(_direct):\n"
    '            with open(_direct, encoding="utf-8") as _f:\n'
    '                _worktree = json.load(_f).get("worktree_path", "") or ""\n'
    "    except Exception as e:\n"
    '        log.debug("pre_tool_use: worktree lookup failed (best-effort): %s", e)\n'
    "else:\n"
    "    # No agent_id/agent_type on this event — a top-level session call (agent_id\n"
    "    # is correctly absent there, no subagent to attribute to) or an older\n"
    "    # harness version. Best-effort LIFO fallback, kept for that case only —\n"
    "    # still ambiguous if 2+ siblings are open at once AND neither the harness\n"
    "    # nor this fallback can identify the caller, but that combination should\n"
    "    # no longer occur given the branch above handles every real subagent call.\n"
    '    agent = data.get("agent_name", "") or "claude-sonnet-5"\n'
    "    try:\n"
    '        _reg_db = os.path.join(DQIII8_ROOT, "database", "dqiii8.db")\n'
    "        if os.path.exists(_reg_db):\n"
    "            import sqlite3 as _rics\n"
    "\n"
    "            _rconn = _rics.connect(_reg_db, timeout=2)\n"
    "            _rrow = _rconn.execute(\n"
    '                "SELECT agent_id, agent_type FROM agent_registry WHERE parent_session=? AND end_time IS NULL "\n'
    '                "ORDER BY start_time DESC LIMIT 1",\n'
    "                (session,),\n"
    "            ).fetchone()\n"
    "            _rconn.close()\n"
    "            if _rrow:\n"
    "                _agent_id, agent = _rrow[0], (_rrow[1] or agent)\n"
    '                _cand = os.path.join(DQIII8_ROOT, "tmp", f"dqiii8_agent_{_rrow[0]}.json")\n'
    "                if os.path.exists(_cand):\n"
    '                    with open(_cand, encoding="utf-8") as _f:\n'
    '                        _worktree = json.load(_f).get("worktree_path", "") or ""\n'
    "    except Exception as e:\n"
    '        log.debug("pre_tool_use: agent lookup failed (best-effort): %s", e)\n'
)

# The diagnostic log line from part 2 has done its job — remove it so hooks.log
# doesn't carry a permanent DEBUG line per tool call.
OLD_DIAG = (
    "# Fase B part 2 diagnostic (temporary, see plan doc): confirm empirically\n"
    "# whether the harness sends any per-tool-call correlator for the subagent\n"
    "# that issued this call, before designing a heuristic-free fix.\n"
    "log.debug(\n"
    '    "pre_tool_use payload diag: keys=%s agent_id=%r agent_name=%r '
    'parent_tool_use_id=%r tool_use_id=%r hook_event_name=%r",\n'
    "    sorted(data.keys()),\n"
    '    data.get("agent_id"),\n'
    '    data.get("agent_name"),\n'
    '    data.get("parent_tool_use_id"),\n'
    '    data.get("tool_use_id"),\n'
    '    data.get("hook_event_name"),\n'
    ")\n"
    "\n"
)
NEW_DIAG = ""

PATCHES = [(OLD_DIAG, NEW_DIAG), (OLD_BLOCK, NEW_BLOCK)]


def apply_patches(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    changed = False
    for old, new in PATCHES:
        if old not in text:
            if new and new in text:
                print(f"  [skip] already applied: {old[:50]!r}...")
            elif not new:
                print(f"  [skip] already removed: {old[:50]!r}...")
            else:
                print(f"  [WARN] pattern not found (already changed?): {old[:50]!r}...")
            continue
        text = text.replace(old, new, 1)
        changed = True
        print(f"  [ok]   patched: {old[:50]!r}...")
    if changed:
        path.write_text(text, encoding="utf-8")
        print(f"  -> wrote {path}")
    else:
        print(f"  -> no changes needed for {path}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hooks-dir", default=str(ROOT_DIR / ".claude" / "hooks"))
    args = ap.parse_args()
    print("== pre_tool_use.py (root fix: use harness-native agent_id directly) ==")
    apply_patches(Path(args.hooks_dir) / "pre_tool_use.py")
    print("== done ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
