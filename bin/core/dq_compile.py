#!/usr/bin/env python3
"""DQIII8 — dq_compile CLI.

Usage:
    python3 -m bin.core.dq_compile "prompt"            # rendered plan to stdout
    python3 -m bin.core.dq_compile --json "prompt"     # full ExecutionPlan as JSON
    python3 -m bin.core.dq_compile --pattern debug "p" # force a pattern
    echo "prompt" | python3 -m bin.core.dq_compile     # stdin
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agents"))

from plan_compiler import dq_compile  # noqa: E402


def main() -> int:
    args = sys.argv[1:]
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    pattern = None
    if "--pattern" in args:
        i = args.index("--pattern")
        try:
            pattern = args[i + 1]
        except IndexError:
            print("error: --pattern requires a value", file=sys.stderr)
            return 2
        del args[i : i + 2]

    if args:
        prompt = " ".join(args)
    elif not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
    else:
        print(__doc__, file=sys.stderr)
        return 2

    try:
        plan = dq_compile(prompt, intent_pattern=pattern)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if as_json:
        d = asdict(plan)
        print(json.dumps(d, ensure_ascii=False, indent=2))
    else:
        print(plan.render())
    return 0


if __name__ == "__main__":
    sys.exit(main())
