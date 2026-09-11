#!/usr/bin/env bash
#
# clone_to_netcup.sh — mirror the DQIII8 core (code + DB snapshot) onto the
# Netcup standby, as part of the Hostinger -> Netcup migration
# (docs/operations/hostinger-to-netcup-runbook.md).
#
# WHY THIS EXISTS
#   Syncthing already replicates /root/dqiii8 to Netcup, but on a best-effort
#   hourly rescan and with no visibility into whether a given run actually
#   landed. This script is the deterministic, on-demand equivalent used before
#   verification checkpoints (Fase 3) and for the final pre-cutover sync
#   (Fase 4) — see the plan/runbook for phase numbers.
#
# SCOPE — deliberately narrow
#   Only the DQIII8 core: bin/, infrastructure/, config/, database/schema_v2.sql,
#   and repo-root files. Explicitly EXCLUDES my-projects/ — that tree is already
#   synced bidirectionally by Syncthing (folder "dqiii8-sync", sendreceive), and
#   a --delete mirror here would remove Netcup-only artifacts (e.g.
#   my-projects/intl-reports/companies/) and, via Syncthing, propagate that
#   deletion back to Hostinger. This script does not touch my-projects/ at all.
#
# NEVER TOUCHES (by design, not by accident)
#   .env, .ssh/, anything under /etc/systemd/ — those are agent-blocked paths
#   (.claude/rules/02_hooks_and_permissions.md) and are provisioned by a human,
#   never by this script. See the runbook for the manual steps.
#
# --delete vs --delete-excluded (post-panel-review correction, 2026-09-06)
#   Uses plain `--delete`, NEVER `--delete-excluded`. `--delete-excluded` also
#   deletes files that match an --exclude pattern at the destination — with
#   .env excluded, that flag would delete the .env a human placed on Netcup on
#   the very next run. Plain `--delete` never removes an excluded file.
#
# REQUIRED ENVIRONMENT
#   DQIII8_BACKUP_HOST   ssh target for Netcup, e.g. a ~/.ssh/config alias
#                        (an alias is preferred: keeps the address out of argv)
#
# OPTIONAL ENVIRONMENT
#   DQIII8_ROOT           local repo root (default: /root/dqiii8)
#   DQIII8_BACKUP_SSH_KEY path to the ssh identity to use
#   DQIII8_BACKUP_PORT    ssh port (default: 22)
#   DQIII8_BACKUP_DRYRUN  set to 1 to pass --dry-run to rsync
#
# USAGE
#   bin/tools/clone_to_netcup.sh              # code + DB snapshot sync
#   bin/tools/clone_to_netcup.sh --final      # same, intended for Fase 4
#                                              # (run only after Hostinger's
#                                              # services/cron are stopped, so
#                                              # the DB snapshot is quiescent)
#
# NON-GOALS
#   Does not install systemd units, does not touch crontab on either side,
#   does not start/stop any service. Copies files and logs what it did.

set -euo pipefail

DQIII8_ROOT="${DQIII8_ROOT:-/root/dqiii8}"
MODE="${1:-}"

log() { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { log "FATAL: $*" >&2; exit 1; }

[ -n "${DQIII8_BACKUP_HOST:-}" ] || die "DQIII8_BACKUP_HOST is unset — refusing to run. Nothing was synced."

command -v rsync >/dev/null 2>&1 || die "rsync not found on PATH"
command -v sqlite3 >/dev/null 2>&1 || die "sqlite3 not found on PATH"

SSH_CMD="ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -p ${DQIII8_BACKUP_PORT:-22}"
if [ -n "${DQIII8_BACKUP_SSH_KEY:-}" ]; then
    SSH_CMD="${SSH_CMD} -i ${DQIII8_BACKUP_SSH_KEY}"
fi

REMOTE_ROOT="dqiii8"  # relative to the ssh user's $HOME on Netcup

RSYNC_OPTS=(-avz --delete --human-readable --partial
            --exclude='.git' --exclude='.git/'
            --exclude='__pycache__' --exclude='*.pyc'
            --exclude='venv/' --exclude='.venv/' --exclude='.venv-core/'
            --exclude='.mcp-venv/' --exclude='venvs/'
            --exclude='.claude/worktrees/'
            --exclude='*.log'
            --exclude='.env' --exclude='.env.*'
            --exclude='my-projects/'
            --exclude='database/')
SIMPLE_RSYNC_OPTS=(-avz)
if [ "${DQIII8_BACKUP_DRYRUN:-0}" = "1" ]; then
    RSYNC_OPTS+=(--dry-run)
    SIMPLE_RSYNC_OPTS+=(--dry-run)
    log "DRY RUN — no files will be transferred"
fi

log "clone start (mode=${MODE:-normal}) — host=${DQIII8_BACKUP_HOST}"

# shellcheck disable=SC2086
$SSH_CMD "${DQIII8_BACKUP_HOST}" "mkdir -p '${REMOTE_ROOT}/database'" \
    || die "cannot reach ${DQIII8_BACKUP_HOST} or cannot create ${REMOTE_ROOT}"

log "syncing DQIII8 core (excluding my-projects/, database/, .env, logs)"
rsync "${RSYNC_OPTS[@]}" -e "${SSH_CMD}" \
    "${DQIII8_ROOT}/" "${DQIII8_BACKUP_HOST}:${REMOTE_ROOT}/" \
    || die "rsync of core tree failed"

# Explicitly re-sync just the schema file (excluded above along with the rest
# of database/, since that dir also holds the live .db and local backups).
if [ -f "${DQIII8_ROOT}/database/schema_v2.sql" ]; then
    rsync "${SIMPLE_RSYNC_OPTS[@]}" -e "${SSH_CMD}" \
        "${DQIII8_ROOT}/database/schema_v2.sql" \
        "${DQIII8_BACKUP_HOST}:${REMOTE_ROOT}/database/schema_v2.sql" \
        || die "rsync of schema_v2.sql failed"
fi

log "ok: core tree synced"

# ── DB snapshot ──────────────────────────────────────────────────────────────
# Never rsync the live .db file directly — it's WAL-mode and may be
# mid-transaction. sqlite3's own .backup API produces a consistent snapshot.
DB_PATH="${DQIII8_ROOT}/database/dqiii8.db"
if [ -f "${DB_PATH}" ]; then
    SNAPSHOT_LOCAL="$(mktemp -t dqiii8-clone-XXXXXX.db)"
    trap 'rm -f "${SNAPSHOT_LOCAL}"' EXIT
    log "snapshotting dqiii8.db via sqlite3 .backup"
    sqlite3 "${DB_PATH}" ".backup '${SNAPSHOT_LOCAL}'" \
        || die "sqlite3 .backup failed"
    rsync "${SIMPLE_RSYNC_OPTS[@]}" -e "${SSH_CMD}" \
        "${SNAPSHOT_LOCAL}" "${DQIII8_BACKUP_HOST}:${REMOTE_ROOT}/database/dqiii8.db" \
        || die "rsync of DB snapshot failed"
    log "ok: dqiii8.db snapshot synced"
else
    log "WARN: ${DB_PATH} not found locally, skipping DB snapshot"
fi

log "clone complete (mode=${MODE:-normal})"
