#!/usr/bin/env bash
# db_backup.sh — daily backup of the DQIII8 databases (added 2026-07-05 remediation).
# Uses sqlite3 .backup (safe on a live WAL database), keeps the last 7 per DB.
# Cron: 0 5 * * *  /root/dqiii8/bin/tools/db_backup.sh >> /tmp/dqiii8_db_backup.log 2>&1
set -euo pipefail

ROOT="${DQIII8_ROOT:-/root/dqiii8}"
DB_DIR="$ROOT/database"
OUT_DIR="$DB_DIR/backups"
KEEP=7
TS="$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "$OUT_DIR"

# Serialize concurrent runs — 2026-08-12 stress test: two unlocked invocations
# can share the same-second $TS and interleave rotation against each other.
exec 9>"$OUT_DIR/.db_backup.lock"
if ! flock -n 9; then
    echo "[db_backup] another instance is already running — skipping" >&2
    exit 0
fi

# Janitor: a prior run killed mid-.backup (disk-full, SIGKILL) leaves a stale
# .partial file. Sweep anything old enough that it can't belong to a run still
# in flight (this run already holds the lock, so nothing else is writing).
find "$OUT_DIR" -maxdepth 1 -name "*.partial" -mmin +60 -print -delete 2>/dev/null \
    | sed 's/^/[db_backup] removing stale partial: /'

failures=0
for db in dqiii8.db dqiii8_metrics.db dqiii8_history.db; do
    src="$DB_DIR/$db"
    [ -f "$src" ] || continue
    dst="$OUT_DIR/${db}.bak-$TS"
    partial="$dst.partial"
    rm -f "$partial"

    if ! sqlite3 "$src" ".backup '$partial'"; then
        echo "[db_backup] ERROR: .backup failed for $db" >&2
        rm -f "$partial"
        failures=$((failures + 1))
        continue
    fi
    # A 0-byte or truncated file (disk-full, killed mid-write) is a valid empty
    # SQLite DB to sqlite3, not a failure — integrity_check on it trivially
    # returns "ok" (2026-08-12 stress test), so size-gate before trusting it.
    if [ ! -s "$partial" ]; then
        echo "[db_backup] ERROR: .backup produced an empty file for $db" >&2
        rm -f "$partial"
        failures=$((failures + 1))
        continue
    fi
    # verify the backup is a readable, consistent database before trusting it.
    # mode=immutable prevents this read-only check from itself creating -wal/-shm
    # sidecars next to $partial (2026-08-12: those sidecars were silently consuming
    # rotation slots below, collapsing real retention from 7 backups to 2).
    if [ "$(sqlite3 "file:$partial?immutable=1" 'PRAGMA integrity_check;' 2>/dev/null)" != "ok" ]; then
        echo "[db_backup] ERROR: integrity_check failed for $db" >&2
        rm -f "$partial"
        failures=$((failures + 1))
        continue
    fi

    chmod 600 "$partial"
    mv -f "$partial" "$dst"
    echo "[db_backup] $TS ok: $dst ($(stat -c%s "$dst") bytes)"

    # rotate: keep newest $KEEP real backups per db, ordered by the timestamp
    # embedded in the filename — not mtime (2026-08-12: production mtimes were
    # already blanket-stamped by an unrelated restore, decoupling eviction order
    # from real backup age). Exclude leftover -wal/-shm sidecars and .partial files.
    find "$OUT_DIR" -maxdepth 1 -name "${db}.bak-*" ! -name '*-wal' ! -name '*-shm' ! -name '*.partial' \
        | sort -r | tail -n "+$((KEEP + 1))" | xargs -r rm -f
done

exit "$((failures > 0 ? 1 : 0))"
