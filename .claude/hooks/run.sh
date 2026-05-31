#!/bin/bash
# Cross-platform Python hook runner.
# Finds python3 or python, then runs the named hook from this directory.
# Returns {} and exits 0 if no Python is found (safe fallback — never blocks Claude Code).
PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
if [ -z "$PY" ]; then
    echo '{}'
    exit 0
fi
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$PY" "$DIR/$1"
