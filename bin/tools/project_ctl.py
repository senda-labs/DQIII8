#!/usr/bin/env python3
"""project_ctl.py — CLI for the project_context SSOT (Stage 2, DB attribution rebuild).

Usage:
  python3 bin/tools/project_ctl.py set <project> [--scope global|<session_id>]
  python3 bin/tools/project_ctl.py get [--scope global|<session_id>]
  python3 bin/tools/project_ctl.py end [--scope global|<session_id>]
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.project_context import end_project, get_project, known_projects, set_project


def main() -> int:
    parser = argparse.ArgumentParser(description="Get/set/end the current project declaration.")
    sub = parser.add_subparsers(dest="action", required=True)

    p_set = sub.add_parser("set", help="Declare the current project.")
    p_set.add_argument("project")
    p_set.add_argument("--scope", default="global")

    p_get = sub.add_parser("get", help="Show the current project for a scope.")
    p_get.add_argument("--scope", default="global")

    p_end = sub.add_parser("end", help="Close the open declaration for a scope.")
    p_end.add_argument("--scope", default="global")

    args = parser.parse_args()

    if args.action == "set":
        try:
            set_project(args.project, scope=args.scope, declared_by="cli")
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            print(f"known projects: {', '.join(sorted(known_projects()))}", file=sys.stderr)
            return 1
        print(f"project set to '{args.project}' for scope '{args.scope}'.")
        if args.scope == "global":
            os.environ["DQIII8_PROJECT"] = args.project
        return 0

    if args.action == "get":
        project = get_project(args.scope)
        print(project if project else f"(no project declared for scope '{args.scope}')")
        return 0

    if args.action == "end":
        closed = end_project(args.scope)
        print("closed." if closed else f"(no open declaration for scope '{args.scope}')")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
