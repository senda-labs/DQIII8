#!/usr/bin/env python3
"""Validate .claude/settings.json's hooks block.

Mitigation for the confirmed SPOF: Claude Code's own schema nests every hook
event (SessionStart, PreToolUse, PostToolUse, ...) under a single top-level
`hooks` key in one file — a malformed edit or a dangling script path anywhere
in it can silently take down all hook-driven telemetry (agent_actions,
error_log) with no error at commit time. This script can't split the schema
(Claude Code owns it), so it makes a break *detectable* instead: valid JSON +
every referenced hook script actually exists. It does NOT check executability
(most commands are invoked as `bash run.sh <script>` or `python3 <script>`,
where the interpreter reads the file regardless of the x-bit, so an x-bit
check would be noise, not signal).

A path outside the repo root (e.g. a globally-installed npm hook) is reported
as a WARNING, not a hard failure — Opus red-team review, 2026-08-13, P2-4:
treating it as fatal would couple every commit in this repo to the lifecycle
of an out-of-repo package (an `npm -g` prune or Node upgrade can relocate it
with no DQIII8 change at all), and the pre-commit caller exits 1 only on
`problems`, not `warnings`.

Usage:
    python3 bin/tools/validate_hooks_config.py [--settings PATH]
Exit code 0 = valid, 1 = invalid (JSON error or missing in-repo script).
"""

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SETTINGS = ROOT / ".claude" / "settings.json"


def _resolve_run_sh_target(run_sh: Path, script_arg: str) -> Path:
    """run.sh resolves its argument relative to its own directory (see
    .claude/hooks/run.sh: exec "$PY" "$DIR/$1")."""
    return run_sh.parent / script_arg


def check_command(command: str) -> tuple[list[str], list[str]]:
    """Return (problems, warnings) for a single hook `command` string."""
    problems, warnings = [], []
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        return [f"unparseable command ({exc}): {command!r}"], warnings
    if not tokens:
        return [f"empty command: {command!r}"], warnings

    # bash .claude/hooks/run.sh <script> — the dominant pattern in this repo.
    if len(tokens) >= 2 and tokens[0] == "bash" and tokens[1].endswith("run.sh"):
        run_sh = (ROOT / tokens[1]) if not os.path.isabs(tokens[1]) else Path(tokens[1])
        if not run_sh.exists():
            problems.append(f"run.sh not found: {run_sh}")
            return problems, warnings
        if len(tokens) < 3:
            problems.append(f"run.sh invoked with no script argument: {command!r}")
            return problems, warnings
        target = _resolve_run_sh_target(run_sh, tokens[2])
        if not target.exists():
            problems.append(f"hook script not found: {target} (via {command!r})")
        return problems, warnings

    # Generic case: first path-like token (contains '/' or a known script
    # extension) is resolved relative to ROOT if not already absolute.
    for tok in tokens[1:] if len(tokens) > 1 else tokens:
        if "/" in tok or tok.endswith((".py", ".sh", ".mjs", ".js")):
            # is_relative_to, not a string prefix (round 2 P2-3): a sibling
            # directory like /root/dqiii8-premium/... starts with the string
            # "/root/dqiii8" and was misclassified as in-repo (hard failure)
            # by the old `.startswith()` check. .resolve() both sides (round 3
            # P3-1): is_relative_to is purely lexical, so an unresolved
            # "/root/dqiii8/../dqiii8-premium/hook.py" token still tested
            # relative-to ROOT and slipped through as in-repo.
            is_out_of_repo = os.path.isabs(tok) and not Path(tok).resolve().is_relative_to(ROOT.resolve())
            path = (Path(tok) if os.path.isabs(tok) else (ROOT / tok)).resolve()
            if not path.exists():
                msg = f"referenced path not found: {path} (via {command!r})"
                (warnings if is_out_of_repo else problems).append(msg)
            break  # only the first path-like token is the target; rest are args
    return problems, warnings


def _staged_or_worktree_text(settings_path: Path) -> str:
    """Read the staged (index) content — only for the pre-commit CLI path,
    which must validate what's about to be committed, not whatever happens to
    be sitting in the worktree (Opus red-team review, 2026-08-13, P2-3).
    Falls back to the worktree file when the path isn't staged (e.g. a direct
    CLI run outside a commit, or the file has no pending changes)."""
    try:
        rel = settings_path.resolve().relative_to(ROOT)
    except ValueError:
        rel = None
    if rel is not None:
        result = subprocess.run(
            ["git", "show", f":{rel.as_posix()}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout
    return settings_path.read_text()


def validate(settings_path: Path) -> list[str]:
    problems, _warnings = _validate(settings_path, source="worktree")
    return problems


def _validate(settings_path: Path, source: str = "worktree") -> tuple[list[str], list[str]]:
    """source='worktree' (default, used by health_watchdog.py and any direct
    caller) reads the live file — the runtime is what's actually executing,
    so that's what must be checked. source='staged' (pre-commit CLI only)
    reads the git index instead. Round 2 P1-3: these were conflated behind
    one always-staged path, so the watchdog — built specifically to catch a
    broken *live* settings.json — silently validated yesterday's committed
    blob instead and could never detect an unstaged break."""
    problems, warnings = [], []
    try:
        raw = _staged_or_worktree_text(settings_path) if source == "staged" else settings_path.read_text()
    except OSError as exc:
        return [f"cannot read {settings_path}: {exc}"], warnings

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [f"invalid JSON in {settings_path}: {exc}"], warnings

    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict):
        return [f"'hooks' key is not an object in {settings_path}"], warnings

    for event_name, entries in hooks.items():
        if not isinstance(entries, list):
            problems.append(f"{event_name}: expected a list of hook groups")
            continue
        for i, group in enumerate(entries):
            for j, hook in enumerate(group.get("hooks", []) if isinstance(group, dict) else []):
                if not isinstance(hook, dict) or hook.get("type") != "command":
                    continue
                command = hook.get("command", "")
                cmd_problems, cmd_warnings = check_command(command)
                for problem in cmd_problems:
                    problems.append(f"{event_name}[{i}].hooks[{j}]: {problem}")
                for warning in cmd_warnings:
                    warnings.append(f"{event_name}[{i}].hooks[{j}]: {warning}")

    return problems, warnings


def main() -> int:
    settings_path = DEFAULT_SETTINGS
    if "--settings" in sys.argv:
        idx = sys.argv.index("--settings") + 1
        if idx >= len(sys.argv):
            print("[validate-hooks] --settings requires a PATH argument", file=sys.stderr)
            return 2
        settings_path = Path(sys.argv[idx])

    problems, warnings = _validate(settings_path, source="staged")
    for w in warnings:
        print(f"[validate-hooks] WARNING: {w}")
    if problems:
        print(f"[validate-hooks] {len(problems)} problem(s) in {settings_path}:")
        for p in problems:
            print(f"  - {p}")
        return 1

    print(f"[validate-hooks] OK — {settings_path} valid, all hook scripts resolved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
