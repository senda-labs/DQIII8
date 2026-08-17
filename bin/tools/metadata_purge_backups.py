#!/usr/bin/env python3
"""Manual, human-invoked deletion of `.bak` files left behind by
metadata_remove.py — separate command, same standing constraint (dry-run
default, --apply --yes required, never wired into CI/hooks).

Only deletes `X.bak` where `X` exists and the audit log
(var/metadata_removal.jsonl) has a matching "written" entry for `X` whose
sha256_before equals sha256(X.bak) (the backup really is what was replaced)
and sha256_after equals sha256(X) (the cleaned file hasn't changed since).
Never a bare `*.bak` glob sweep — a `.bak` with no matching log entry is
left alone and reported, not deleted. No overwrite-then-unlink "secure
delete" — on this VPS's ext4/NVMe that offers no real guarantee, and
claiming one would contradict the C2PA soft-binding disclosure this same
toolchain makes elsewhere.

Usage:
    python3 bin/tools/metadata_purge_backups.py --dir PATH               # dry run
    python3 bin/tools/metadata_purge_backups.py --dir PATH --apply --yes
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from metadata_lib.audit_log import LOG_PATH  # noqa: E402
from metadata_lib.validate import sha256  # noqa: E402

DEFAULT_MAX_FILES = 5000


def _load_log_entries() -> list[dict]:
    if not LOG_PATH.exists():
        return []
    entries = []
    with LOG_PATH.open("r") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _find_backups(root: Path, max_files: int) -> list[Path]:
    found = []
    for p in root.rglob("*.bak"):
        if p.is_symlink():
            continue
        if not p.is_file():
            continue
        found.append(p)
        if len(found) >= max_files:
            break
    return sorted(found)


def _path_matches(logged: str, target: Path) -> bool:
    """Absolute log entries are compared resolved; relative ones are not.

    metadata_remove now records absolute paths, so a purge run from any cwd finds
    them. Legacy *relative* entries are deliberately left on raw string equality:
    resolving them would bind them to the purge run's cwd, which has no relationship
    to the removal run's cwd that produced them, and could therefore match a
    same-named file somewhere else entirely.
    """
    p = Path(logged)
    if not p.is_absolute():
        return logged == str(target)
    try:
        return p.resolve() == target.resolve()
    except OSError:
        return False


def _match(entries: list[dict], target: Path, bak_sha: str, target_sha: str) -> dict | None:
    best = None
    for e in entries:
        if e.get("outcome") != "written":
            continue
        if not _path_matches(e.get("path") or "", target):
            continue
        if e.get("sha256_before") == bak_sha and e.get("sha256_after") == target_sha:
            best = e
    return best


def process(root: Path, *, apply: bool, yes: bool, max_files: int) -> list[dict]:
    entries = _load_log_entries()
    results = []
    for bak_path in _find_backups(root, max_files):
        target = bak_path.with_suffix("") if bak_path.suffix == ".bak" else Path(str(bak_path)[: -len(".bak")])
        if not target.exists() or target.is_symlink():
            results.append({"bak": str(bak_path), "status": "orphan_no_target"})
            continue
        try:
            bak_sha = sha256(bak_path.read_bytes())
            target_sha = sha256(target.read_bytes())
        except OSError as e:
            results.append({"bak": str(bak_path), "status": "unreadable", "note": str(e)})
            continue

        match = _match(entries, target, bak_sha, target_sha)
        if match is None:
            results.append({"bak": str(bak_path), "status": "no_matching_audit_entry"})
            continue

        removed_summary = match.get("removed", [])
        if not apply:
            results.append(
                {
                    "bak": str(bak_path),
                    "status": "dry_run",
                    "target": str(target),
                    "would_remove": removed_summary,
                }
            )
            continue
        if not yes:
            results.append({"bak": str(bak_path), "status": "refused_needs_yes"})
            continue

        try:
            bak_path.unlink()
        except OSError as e:
            results.append({"bak": str(bak_path), "status": "delete_failed", "note": str(e)})
            continue
        results.append({"bak": str(bak_path), "status": "deleted", "target": str(target), "removed": removed_summary})

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES)
    args = parser.parse_args()

    if not args.dir.is_dir():
        print(f"metadata-purge-backups: not a directory: {args.dir}", file=sys.stderr)
        return 2
    if args.apply and not args.yes:
        print("metadata-purge-backups: --apply also needs --yes (explicit confirmation).", file=sys.stderr)
        return 2

    results = process(args.dir, apply=args.apply, yes=args.yes, max_files=args.max_files)

    if args.json:
        print(json.dumps({"results": results}, indent=2))
    else:
        deleted = [r for r in results if r["status"] == "deleted"]
        dry = [r for r in results if r["status"] == "dry_run"]
        skipped = [r for r in results if r["status"] not in ("deleted", "dry_run")]
        for r in skipped:
            print(f"  skip ({r['status']}): {r['bak']}{' — ' + r.get('note', '') if r.get('note') else ''}", file=sys.stderr)
        if args.apply:
            print(f"metadata-purge-backups: deleted {len(deleted)} backup(s). {len(skipped)} skipped.")
        else:
            print(f"metadata-purge-backups: DRY RUN — {len(dry)} backup(s) eligible for deletion, {len(skipped)} skipped. Re-run with --apply --yes to delete.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
