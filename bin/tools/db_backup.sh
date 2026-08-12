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

for db in dqiii8.db dqiii8_metrics.db dqiii8_history.db; do
    src="$DB_DIR/$db"
    [ -f "$src" ] || continue
    dst="$OUT_DIR/${db}.bak-$TS"
    sqlite3 "$src" ".backup '$dst'"
    # verify the backup is a readable, consistent database before trusting it.
    # mode=immutable prevents this read-only check from itself creating -wal/-shm
    # sidecars next to $dst (2026-08-12: those sidecars were silently consuming
    # rotation slots below, collapsing real retention from 7 backups to 2).
    if [ "$(sqlite3 "file:$dst?immutable=1" 'PRAGMA integrity_check;')" != "ok" ]; then
        echo "[db_backup] ERROR: integrity_check failed for $dst" >&2
        rm -f "$dst"
        exit 1
    fi
    chmod 600 "$dst"
    echo "[db_backup] $TS ok: $dst ($(stat -c%s "$dst") bytes)"
    # rotate: keep newest $KEEP real backups per db (exclude any leftover -wal/-shm
    # sidecars from before the immutable-URI fix above, so they can't eat KEEP slots)
    find "$OUT_DIR" -maxdepth 1 -name "${db}.bak-*" ! -name '*-wal' ! -name '*-shm' \
        -printf '%T@ %p\n' 2>/dev/null | sort -rn | tail -n "+$((KEEP + 1))" | cut -d' ' -f2- \
        | xargs -r rm -f
done
