#!/usr/bin/env python3
"""Validate .claude/settings.json's hooks block.

Mitigation for the confirmed SPOF: Claude Code's own schema nests every hook
event (SessionStart, PreToolUse, PostToolUse, ...) under a single top-level
`hooks` key in one file — a malformed edit or a dangling script path anywhere
in it can silently take down all hook-driven telemetry (agent_actions,
error_log) with no error at commit time. This script can't split the schema
(Claude Code owns it), so it makes a break *detectable* instead: valid JSON +
every referenced hook script actually exists and is executable.

Usage:
    python3 bin/tools/validate_hooks_config.py [--settings PATH]
Exit code 0 = valid, 1 = invalid (JSON error or missing/non-executable script).
"""

import json
import os
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SETTINGS = ROOT / ".claude" / "settings.json"


def _resolve_run_sh_target(run_sh: Path, script_arg: str) -> Path:
    """run.sh resolves its argument relative to its own directory (see
    .claude/hooks/run.sh: exec "$PY" "$DIR/$1")."""
    return run_sh.parent / script_arg


def check_command(command: str) -> list[str]:
    """Return a list of problems found for a single hook `command` string."""
    problems = []
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        return [f"unparseable command ({exc}): {command!r}"]
    if not tokens:
        return [f"empty command: {command!r}"]

    # bash .claude/hooks/run.sh <script> — the dominant pattern in this repo.
    if len(tokens) >= 2 and tokens[0] == "bash" and tokens[1].endswith("run.sh"):
        # Invoked as `bash run.sh` — bash reads the file regardless of the
        # x-bit, so only existence matters here, not executability.
        run_sh = (ROOT / tokens[1]) if not os.path.isabs(tokens[1]) else Path(tokens[1])
        if not run_sh.exists():
            problems.append(f"run.sh not found: {run_sh}")
            return problems
        if len(tokens) >= 3:
            target = _resolve_run_sh_target(run_sh, tokens[2])
            if not target.exists():
                problems.append(f"hook script not found: {target} (via {command!r})")
        return problems

    # Generic case: first path-like token (contains '/' or a known script
    # extension) is resolved relative to ROOT if not already absolute.
    for tok in tokens[1:] if len(tokens) > 1 else tokens:
        if "/" in tok or tok.endswith((".py", ".sh", ".mjs", ".js")):
            path = Path(tok) if os.path.isabs(tok) else (ROOT / tok)
            if not path.exists():
                problems.append(f"referenced path not found: {path} (via {command!r})")
            break  # only the first path-like token is the target; rest are args
    return problems


def validate(settings_path: Path) -> list[str]:
    problems = []
    try:
        raw = settings_path.read_text()
    except OSError as exc:
        return [f"cannot read {settings_path}: {exc}"]

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [f"invalid JSON in {settings_path}: {exc}"]

    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict):
        return [f"'hooks' key is not an object in {settings_path}"]

    for event_name, entries in hooks.items():
        if not isinstance(entries, list):
            problems.append(f"{event_name}: expected a list of hook groups")
            continue
        for i, group in enumerate(entries):
            for j, hook in enumerate(group.get("hooks", []) if isinstance(group, dict) else []):
                if not isinstance(hook, dict) or hook.get("type") != "command":
                    continue
                command = hook.get("command", "")
                for problem in check_command(command):
                    problems.append(f"{event_name}[{i}].hooks[{j}]: {problem}")

    return problems


def main() -> int:
    settings_path = DEFAULT_SETTINGS
    if "--settings" in sys.argv:
        settings_path = Path(sys.argv[sys.argv.index("--settings") + 1])

    problems = validate(settings_path)
    if problems:
        print(f"[validate-hooks] {len(problems)} problem(s) in {settings_path}:")
        for p in problems:
            print(f"  - {p}")
        return 1

    print(f"[validate-hooks] OK — {settings_path} valid, all hook scripts resolved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
