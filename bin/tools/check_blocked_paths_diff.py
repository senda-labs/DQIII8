#!/usr/bin/env python3
"""
DQIII8 — Blocked-path diff scanner (Rango 1 residual, 2026-08-19 red-team audit).

The pre-push hook's gitleaks pass only catches secret-*shaped* content — a
committed empty/placeholder `id_rsa` or `.env` file has no secret shape but
still shouldn't leave the machine. Reuses `_blocked_path_hit()` from
permission_analyzer.py (the live BLOCKED_PATHS SSOT) instead of restating the
list here, per 02_hooks_and_permissions.md's no-duplication rule.

Only paths that are genuinely NEW at `base_ref` (a schema/secrets-*shaped*
filename appearing for the first time) are flagged -- a path already present
at `base_ref` was already reviewed by every prior gate that let it land
there, so a routine content update (e.g. a legitimate schema_v2.sql migration
or a black-formatting pass on a *_secrets.py stub) must not re-trip this
check on every future push forever. Found live 2026-08-21 during a
replace-tree premium sync: both database/schema_v2.sql and
bin/core/human_pending/secrets.py already existed, unchanged in purpose, on
both sides -- content-only diffs, confirmed leak-free by gitleaks and by
manual diff review, yet blocked every time regardless. Without `base_ref`
(the legacy 1-arg call, e.g. a brand-new remote branch with no prior tip),
every path is still treated as new -- unchanged, conservative behavior.

Usage: check_blocked_paths_diff.py <git-log-opts-range> [base-ref]
Exits 1 (blocks the push) if any changed path in that range matches
BLOCKED_PATHS and did not already exist at base-ref; 0 otherwise.
"""

import subprocess
import sys
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parent.parent.parent / ".claude" / "hooks"
sys.path.insert(0, str(_HOOKS_DIR))
from permission_analyzer import _blocked_path_hit  # noqa: E402


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print("usage: check_blocked_paths_diff.py <git-log-opts-range> [base-ref]", file=sys.stderr)
        return 2
    log_opts = sys.argv[1]
    base_ref = sys.argv[2] if len(sys.argv) == 3 else None

    result = subprocess.run(
        ["git", "log", log_opts, "--name-only", "--pretty=format:"],
        capture_output=True,
        text=True,
        check=True,
    )
    paths = {line.strip() for line in result.stdout.splitlines() if line.strip()}

    already_tracked = set()
    if base_ref:
        base_result = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", base_ref],
            capture_output=True,
            text=True,
        )
        if base_result.returncode == 0:
            already_tracked = {
                line.strip() for line in base_result.stdout.splitlines() if line.strip()
            }

    hits = [
        (p, blocked)
        for p in paths
        if p not in already_tracked and (blocked := _blocked_path_hit(p))
    ]
    if hits:
        print(
            "[check-blocked-paths] BLOCKED_PATHS matched in the commits about to be pushed:",
            file=sys.stderr,
        )
        for path, blocked in hits:
            print(f"  {path}  (matches '{blocked}')", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
