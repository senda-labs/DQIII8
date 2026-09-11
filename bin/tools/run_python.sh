#!/usr/bin/env bash
#
# run_python.sh — resolve the correct Python interpreter for the current
# working directory and exec the given script through it.
#
# WHY THIS EXISTS
#   infrastructure/cron/dqiii8.crontab is a single file shared by Hostinger
#   and Netcup (deliberately, to avoid the two hosts' cron drifting apart —
#   see docs/operations/hostinger-to-netcup-runbook.md). Hostinger installs
#   its Python deps into system Python; Netcup (Debian 13, PEP 668) can only
#   install them into .venv-core/ (same host split as the systemd layer, see
#   infrastructure/systemd/netcup-overrides/README.md). Some sub-projects
#   (e.g. my-projects/football-value) carry their own separate .venv/ too.
#   A crontab entry that calls bare "python3" resolves to whichever system
#   Python is on PATH, on every host — right on Hostinger, wrong on Netcup,
#   where it silently runs jobs against an interpreter with none of
#   requirements.txt installed (found 2026-09-07 via health_watchdog's own
#   false readings: "psutil not installed", "sqlite-vec 0.1.9 != expected
#   0.1.7" — both true statements about system Python, irrelevant to the
#   venv the services actually run from).
#
#   Resolved relative to $PWD first, not a hardcoded root, because every
#   crontab line already does `cd <project-dir> &&` before invoking this —
#   so a project with its own venv (.venv-core for the dqiii8 core, .venv
#   for football-value) gets it. A sub-project with no venv of its own
#   (global-media-org, lier, ...) falls back to the dqiii8 core's shared
#   .venv-core — same convention Hostinger already has for free (one shared
#   system Python for everything) — before finally falling back to plain
#   python3. Found 2026-09-07 the hard way: city_blocks_ctl.py's tmux
#   workers crash-looped on ModuleNotFoundError until this fallback tier
#   was added — global-media-org has no venv of its own, so the first two
#   checks always missed and it silently ran under bare system python3.
#
#   Each candidate is verified with `-m pip --version`, not just "the path
#   exists" — Hostinger has a stale, half-created .venv-core (abandoned
#   2026-08-13 experiment, `pip` script present but the `pip` module itself
#   missing) that a plain path-exists check would happily pick over the
#   real, fully-populated system Python. A candidate that can't even run
#   its own pip is not a usable interpreter for anything real.
#
# USAGE (from crontab, always with an explicit `cd <dir> &&` first)
#   bin/tools/run_python.sh path/to/script.py [args...]
set -euo pipefail
DQIII8_ROOT="${DQIII8_ROOT:-/root/dqiii8}"

_usable() {
    [ -x "$1" ] && "$1" -m pip --version >/dev/null 2>&1
}

if _usable ".venv-core/bin/python3"; then
    exec ".venv-core/bin/python3" "$@"
elif _usable ".venv/bin/python3"; then
    exec ".venv/bin/python3" "$@"
elif _usable "${DQIII8_ROOT}/.venv-core/bin/python3"; then
    exec "${DQIII8_ROOT}/.venv-core/bin/python3" "$@"
else
    exec python3 "$@"
fi
