"""Write-safety scaffolding shared by every fmt_* remover.

Write order (never violate): transform in memory -> write tmp -> VALIDATE tmp
-> write .bak from original (refuse if .bak exists) -> os.replace(tmp, path).
Validation always happens before any irreversible action. safeio itself does
not validate (that's validate.py's job, format-specific) — it only provides
the atomic primitives and enforces the ordering contract via write_result().
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MAX_DIR_FILES = 5000
DEFAULT_MAX_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB cumulative budget
EXCLUDED_SUFFIXES = (".bak", ".tmp")


@dataclass
class WriteResult:
    written: bool
    backup_path: Path | None
    reason: str = ""


def refuses_symlink(path: Path) -> bool:
    return path.is_symlink()


def write_new_file(path: Path, data: bytes, *, mode: int | None = None) -> None:
    """Create `path` and write `data` — the ONLY sanctioned way this toolchain
    creates its `.bak`/`.tmp` side files.

    O_CREAT|O_EXCL makes a pre-planted symlink (dangling or not) fail with
    EEXIST instead of being followed, so an attacker cannot redirect the write
    to an arbitrary victim path; O_NOFOLLOW is kept as a second, explicit
    barrier so the guarantee does not rest on one flag's semantics alone.
    Raises FileExistsError if anything already occupies `path`.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
    except BaseException:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    if mode is not None:
        os.chmod(path, mode)


def make_tempdir_same_fs(target: Path) -> Path:
    """A per-invocation tempdir on the SAME filesystem as target's parent, so
    the eventual os.replace() stays atomic. Refuses (raises) rather than
    silently falling back to /tmp on a different filesystem.
    """
    parent = target.resolve().parent
    if not os.access(parent, os.W_OK):
        raise PermissionError(f"parent directory not writable: {parent}")
    return Path(tempfile.mkdtemp(dir=parent, prefix=".mdtmp-"))


def atomic_replace(path: Path, new_bytes: bytes, *, backup_from: bytes) -> WriteResult:
    """The only function that actually mutates `path`. Caller MUST have
    already validated `new_bytes` (e.g. via validate.py) before calling this
    — this function does no validation itself, it only performs the final
    backup+replace step atomically.
    """
    if refuses_symlink(path):
        return WriteResult(False, None, "symlink refused")

    bak = path.with_name(path.name + ".bak")
    # is_symlink() first: a dangling symlink makes exists() False, and the
    # O_EXCL open below would then be the only thing standing between us and
    # a redirected write — report it as the refusal it is, not as a crash.
    if bak.is_symlink() or bak.exists():
        return WriteResult(False, None, "backup already exists, resolve it first")

    try:
        mode = path.stat().st_mode
    except OSError:
        mode = None

    tmp = path.with_name(path.name + ".tmp")
    try:
        write_new_file(tmp, new_bytes, mode=mode)
    except FileExistsError:
        return WriteResult(False, None, "a .tmp already exists (stale or concurrent run), resolve it first")

    # backup only taken once we're certain we're about to succeed
    try:
        write_new_file(bak, backup_from, mode=mode)
    except FileExistsError:
        tmp.unlink(missing_ok=True)
        return WriteResult(False, None, "backup already exists, resolve it first")
    except OSError:
        tmp.unlink(missing_ok=True)
        raise

    os.replace(tmp, path)
    return WriteResult(True, bak)


def iter_files(
    root: Path,
    *,
    max_files: int = DEFAULT_MAX_DIR_FILES,
    max_bytes: int = DEFAULT_MAX_BYTES,
):
    """Lazily walk `root`, yielding (path, skip_reason_or_None). Bounds work
    done DURING collection (not just the reported count) — os.walk descends
    incrementally and the loop breaks the moment either cap is hit, unlike
    `sorted(root.rglob('*'))` which materializes the whole tree first.

    Skips symlinks (files and directories — os.walk with followlinks=False,
    the default, does not descend into symlinked directories) and excludes
    this tool's own *.bak/*.tmp artifacts from the sweep.
    """
    count = 0
    cum_bytes = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in sorted(dirnames) if not Path(dirpath, d).is_symlink()]
        for name in sorted(filenames):
            p = Path(dirpath, name)
            if p.is_symlink():
                yield p, "symlink"
                continue
            if p.suffix in EXCLUDED_SUFFIXES:
                continue
            if count >= max_files:
                yield None, f"stopped after {max_files} files (more remain) — narrow the target"
                return
            try:
                size = p.stat().st_size
            except OSError:
                yield p, "unreadable"
                continue
            if cum_bytes + size > max_bytes:
                yield None, f"stopped after {max_bytes} cumulative bytes (more remain) — narrow the target"
                return
            count += 1
            cum_bytes += size
            yield p, None
