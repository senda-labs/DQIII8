#!/usr/bin/env bash
# db_restore.sh — restore a DQIII8 database from a db_backup.sh snapshot.
# Companion to db_backup.sh; no restore procedure existed before this (found
# by the 2026-08-21 6-Opus panel, resilience lens, and verified as a real gap:
# backups exist and are integrity-checked at write time, but nothing ever
# proved a restore actually works end to end).
#
# Run from a non-Claude-Code shell (SSH/tmux), same reason as
# db_consolidate.py: this stops the writer units for the duration of the
# restore, and an agent session's own hooks are among those writers.
#
# Usage:
#   bin/tools/db_restore.sh <db-name> [backup-timestamp]
#   bin/tools/db_restore.sh dqiii8.db                       # latest backup
#   bin/tools/db_restore.sh dqiii8.db 20260821T025001Z      # specific backup
#   bin/tools/db_restore.sh dqiii8_knowledge.db --list      # list available backups
set -euo pipefail

ROOT="${DQIII8_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
DB_DIR="$ROOT/database"
OUT_DIR="$DB_DIR/backups"
UNITS=(dqiii8-bot dq-dashboard cron hpt-poller.timer dqiii8-health.timer)

DB_NAME="${1:-}"
SELECTOR="${2:-}"

if [ -z "$DB_NAME" ]; then
    echo "Usage: $0 <db-name> [backup-timestamp|--list]" >&2
    exit 1
fi

if [ "$SELECTOR" = "--list" ]; then
    find "$OUT_DIR" -maxdepth 1 -name "${DB_NAME}.bak-*" -not -name "*.partial" | sort -r
    exit 0
fi

if [ -n "$SELECTOR" ]; then
    SRC="$OUT_DIR/${DB_NAME}.bak-${SELECTOR}"
else
    SRC="$(find "$OUT_DIR" -maxdepth 1 \
        -name "${DB_NAME}.bak-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z" \
        | sort -r | head -n1)"
fi

if [ -z "$SRC" ] || [ ! -f "$SRC" ]; then
    echo "[db_restore] ERROR: no backup found for '$DB_NAME' (selector: '${SELECTOR:-latest}')" >&2
    exit 1
fi

echo "[db_restore] chosen backup: $SRC"
if [ "$(sqlite3 "file:$SRC?immutable=1" 'PRAGMA integrity_check;' 2>/dev/null)" != "ok" ]; then
    echo "[db_restore] ERROR: integrity_check failed for backup $SRC — refusing to restore from it" >&2
    exit 1
fi
echo "[db_restore] backup integrity_check: ok"

DST="$DB_DIR/$DB_NAME"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
PRE_RESTORE="$OUT_DIR/${DB_NAME}.pre-restore-${TS}"

if [ -f "$DST" ]; then
    cp "$DST" "$PRE_RESTORE"
    echo "[db_restore] safety copy of current live file -> $PRE_RESTORE"
fi

echo "[db_restore] stopping writer units: ${UNITS[*]}"
systemctl stop "${UNITS[@]}" || true

cp "$SRC" "$DST"
rm -f "$DST-wal" "$DST-shm"
chmod 600 "$DST"

if [ "$(sqlite3 "file:$DST?immutable=1" 'PRAGMA integrity_check;' 2>/dev/null)" != "ok" ]; then
    echo "[db_restore] ERROR: integrity_check failed AFTER restore — restoring the pre-restore safety copy" >&2
    if [ -f "$PRE_RESTORE" ]; then
        cp "$PRE_RESTORE" "$DST"
    fi
    systemctl start "${UNITS[@]}" || true
    exit 1
fi

echo "[db_restore] restored $DB_NAME from $SRC, post-restore integrity_check: ok"
echo "[db_restore] restarting writer units"
systemctl start "${UNITS[@]}" || true

echo "[db_restore] done. Pre-restore safety copy kept at: ${PRE_RESTORE:-<none, $DST did not exist before>}"
