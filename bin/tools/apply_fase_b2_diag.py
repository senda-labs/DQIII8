#!/usr/bin/env python3
"""Fase B, part 2 — root-cause investigation for concurrent-sibling ambiguity.

Stress-testing Fase A found that two concurrent subagents under the same
session can get their raw agent_actions rows cross-attributed (the LIFO
resolution in pre_tool_use.py picks "most recently started sibling",
independent of whether that sibling already finished, and with no way to
disambiguate at all when two siblings are open at the same instant).

Applies, idempotently:
  1. A one-line DEBUG log of the real PreToolUse/PostToolUse payload shape
     (keys + a few candidate correlator fields) — nobody in this repo has
     ever empirically confirmed what Claude Code actually sends here; the
     existing code's assumption that agent_id/agent_name are absent is an
     inference from the fallback logic's existence, not a verified fact.
  2. `AND end_time IS NULL` on the LIFO fallback query — excludes already
     finished siblings from candidacy. Does not fix true simultaneous
     overlap (two siblings open at once), only misattribution to a sibling
     that already closed.

Run by hand, outside any agent session. Safe to re-run.

Usage: python3 bin/tools/apply_fase_b2_diag.py [--hooks-dir PATH]
"""

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

PATCHES = [
    (
        "try:\n"
        "    data = json.load(sys.stdin)\n"
        "except Exception as e:\n"
        '    log.warning("pre_tool_use: stdin parse failed: %s", e)\n'
        "    sys.exit(0)\n",
        "try:\n"
        "    data = json.load(sys.stdin)\n"
        "except Exception as e:\n"
        '    log.warning("pre_tool_use: stdin parse failed: %s", e)\n'
        "    sys.exit(0)\n"
        "\n"
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
        ")\n",
    ),
    (
        "                _rrow = _rconn.execute(\n"
        '                    "SELECT agent_id FROM agent_registry WHERE parent_session=? "\n'
        '                    "ORDER BY start_time DESC LIMIT 1",\n'
        "                    (session,),\n"
        "                ).fetchone()  # Rango 6 CEILING: ambiguous with concurrent siblings — no per-agent disambiguator flows through this hook's stdin today\n",
        "                _rrow = _rconn.execute(\n"
        '                    "SELECT agent_id FROM agent_registry WHERE parent_session=? AND end_time IS NULL "\n'
        '                    "ORDER BY start_time DESC LIMIT 1",\n'
        "                    (session,),\n"
        "                ).fetchone()  # Rango 6 CEILING (narrowed, Fase B part 2): excludes siblings that already\n"
        "                # closed — still ambiguous if 2+ siblings are open at the same instant, that needs a\n"
        "                # harness-provided per-call correlator dqiii8 does not have today.\n",
    ),
]


def apply_patches(path: Path, patches: list[tuple[str, str]]) -> None:
    text = path.read_text(encoding="utf-8")
    changed = False
    for old, new in patches:
        if new in text:
            print(f"  [skip] already applied in {path.name}: {old[:50]!r}...")
            continue
        if old not in text:
            print(f"  [WARN] pattern not found in {path.name} (file changed?): {old[:50]!r}...")
            continue
        text = text.replace(old, new, 1)
        changed = True
        print(f"  [ok]   patched {path.name}: {old[:50]!r}...")
    if changed:
        path.write_text(text, encoding="utf-8")
        print(f"  -> wrote {path}")
    else:
        print(f"  -> no changes needed for {path}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hooks-dir", default=str(ROOT_DIR / ".claude" / "hooks"))
    args = ap.parse_args()
    print("== pre_tool_use.py (diagnostic + LIFO narrowing) ==")
    apply_patches(Path(args.hooks_dir) / "pre_tool_use.py", PATCHES)
    print("== done ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
