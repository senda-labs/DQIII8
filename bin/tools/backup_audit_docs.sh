#!/usr/bin/env bash
#
# backup_audit_docs.sh — off-VPS backup of the audit/findings corpus.
#
# WHY THIS EXISTS
#   `docs/audits/` is gitignored (deliberately — see .gitignore, F-26 leak of
#   2026-08-17) and `database/audit_reports/*.md` is only narrowly un-ignored.
#   Several rules and skills cite `docs/audits/` as a source of truth, yet a
#   single `rm -rf` or a lost VPS would take the whole ledger with it. Git is
#   therefore NOT the durability mechanism for this corpus. This script is.
#
# MUTUAL-BACKUP PATTERN (Netcup <-> Hostinger)
#   Both VPS run this same script against each other. The script is deliberately
#   side-agnostic: it has no idea whether it is "the Netcup one" or "the
#   Hostinger one". Direction is decided purely by the environment variables set
#   locally on each host at cron/systemd time:
#
#     on Netcup:     DQIII8_BACKUP_HOST=<hostinger ssh target>
#     on Hostinger:  DQIII8_BACKUP_HOST=<netcup ssh target>
#
#   That gives two independent one-directional jobs, one per host, and no host
#   holds the other's inbound credentials. No real IP or hostname is hardcoded
#   here — per the gitignore/secret invariant, infra addresses never live in a
#   committed file.
#
# REQUIRED ENVIRONMENT
#   DQIII8_BACKUP_HOST   ssh target for the *remote* peer, e.g. user@host or a
#                        ~/.ssh/config alias (an alias is preferred: it keeps the
#                        address out of the crontab too).
#   DQIII8_BACKUP_PATH   absolute base directory on the remote peer, e.g.
#                        /srv/dqiii8-backups
#
# OPTIONAL ENVIRONMENT
#   DQIII8_ROOT          local repo root (default: /root/dqiii8)
#   DQIII8_BACKUP_SSH_KEY  path to the ssh identity to use
#   DQIII8_BACKUP_PORT   ssh port (default: 22)
#   DQIII8_BACKUP_DRYRUN set to 1 to pass --dry-run to rsync
#
# INSTALLATION (NOT performed by this script — install by hand on each host)
#   Neither a crontab nor a systemd timer is written by this repo; wiring live
#   scheduling is an operational action, and it needs the peer's real address and
#   SSH key, which are not in git. Install ONE of the following on EACH of the
#   two hosts, with that host's own peer address:
#
#   (a) crontab -e  — daily at 03:20, jittered per host so the two don't collide:
#         20 3 * * * DQIII8_BACKUP_HOST=dqiii8-peer DQIII8_BACKUP_PATH=/srv/dqiii8-backups /root/dqiii8/bin/tools/backup_audit_docs.sh >> /root/dqiii8/var/backup_audit_docs.log 2>&1
#
#   (b) systemd — /etc/systemd/system/dqiii8-audit-backup.service plus
#       /etc/systemd/system/dqiii8-audit-backup.timer, then
#       `systemctl enable --now dqiii8-audit-backup.timer`:
#         # .timer
#         [Timer]
#         OnCalendar=*-*-* 03:20:00
#         RandomizedDelaySec=900
#         Persistent=true
#
# NON-GOALS
#   No counter-attack, no active response, no offensive logic of any kind. This
#   script copies files and logs what it did. Nothing else.

set -euo pipefail

DQIII8_ROOT="${DQIII8_ROOT:-/root/dqiii8}"

log() { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { log "FATAL: $*" >&2; exit 1; }

# ── Fail closed on missing configuration ────────────────────────────────────
# An unset target must be a loud failure, not a silent no-op that looks like a
# successful backup in the cron log.
[ -n "${DQIII8_BACKUP_HOST:-}" ] || die "DQIII8_BACKUP_HOST is unset — refusing to run. Nothing was backed up."
[ -n "${DQIII8_BACKUP_PATH:-}" ] || die "DQIII8_BACKUP_PATH is unset — refusing to run. Nothing was backed up."

case "${DQIII8_BACKUP_PATH}" in
    /*) ;;
    *) die "DQIII8_BACKUP_PATH must be an absolute path, got: ${DQIII8_BACKUP_PATH}" ;;
esac

command -v rsync >/dev/null 2>&1 || die "rsync not found on PATH"

# ── Dated snapshot directory ────────────────────────────────────────────────
# Deliberately NOT a `--delete` mirror. A mirror propagates this host's
# accidental deletion straight to the peer, which is the exact loss scenario
# the backup exists to prevent. Each run writes into its own dated directory and
# hard-links unchanged files against the previous run (--link-dest), so the cost
# of keeping history is close to the cost of a mirror while deletions on the
# source can never remove anything already backed up.
#
# --delete-excluded is still used *within* the snapshot: if the exclude list
# grows, a file that is now excluded should not linger in a partially-written
# snapshot directory from a retry of the same day.
SNAPSHOT="$(date -u +%Y-%m-%d)"
REMOTE_BASE="${DQIII8_BACKUP_PATH%/}"
REMOTE_DEST="${REMOTE_BASE}/${SNAPSHOT}"
REMOTE_LATEST="${REMOTE_BASE}/latest"

SSH_CMD="ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -p ${DQIII8_BACKUP_PORT:-22}"
if [ -n "${DQIII8_BACKUP_SSH_KEY:-}" ]; then
    SSH_CMD="${SSH_CMD} -i ${DQIII8_BACKUP_SSH_KEY}"
fi

RSYNC_OPTS=(-avz --delete-excluded --human-readable --partial
            --exclude='*.tmp' --exclude='*.swp' --exclude='.DS_Store'
            --link-dest="${REMOTE_LATEST}")
if [ "${DQIII8_BACKUP_DRYRUN:-0}" = "1" ]; then
    RSYNC_OPTS+=(--dry-run)
    log "DRY RUN — no files will be transferred"
fi

# Sources. Trailing slash matters: copy the *contents* into a same-named
# subdirectory of the snapshot, so both corpora stay distinguishable remotely.
SOURCES=("docs/audits" "database/audit_reports")

log "backup start — host=${DQIII8_BACKUP_HOST} snapshot=${SNAPSHOT}"

# The remote directories must exist before rsync writes into them.
# shellcheck disable=SC2086
$SSH_CMD "${DQIII8_BACKUP_HOST}" "mkdir -p '${REMOTE_DEST}'" \
    || die "cannot reach ${DQIII8_BACKUP_HOST} or cannot create ${REMOTE_DEST}"

failures=0
for rel in "${SOURCES[@]}"; do
    src="${DQIII8_ROOT}/${rel}"
    if [ ! -d "${src}" ]; then
        log "WARN: source missing, skipping: ${src}"
        continue
    fi
    name="$(basename "${rel}")"
    count="$(find "${src}" -type f | wc -l)"
    log "syncing ${rel} (${count} files) -> ${DQIII8_BACKUP_HOST}:${REMOTE_DEST}/${name}/"
    if rsync "${RSYNC_OPTS[@]}" -e "${SSH_CMD}" \
        "${src}/" "${DQIII8_BACKUP_HOST}:${REMOTE_DEST}/${name}/"; then
        log "ok: ${rel}"
    else
        log "ERROR: rsync failed for ${rel}"
        failures=$((failures + 1))
    fi
done

if [ "${failures}" -eq 0 ] && [ "${DQIII8_BACKUP_DRYRUN:-0}" != "1" ]; then
    # Repoint `latest` only after every source succeeded, so a half-finished
    # snapshot never becomes the --link-dest baseline for the next run.
    # shellcheck disable=SC2086
    $SSH_CMD "${DQIII8_BACKUP_HOST}" \
        "ln -sfn '${REMOTE_DEST}' '${REMOTE_LATEST}.new' && mv -Tf '${REMOTE_LATEST}.new' '${REMOTE_LATEST}'" \
        || log "WARN: could not update ${REMOTE_LATEST} symlink"
    log "latest -> ${REMOTE_DEST}"
fi

if [ "${failures}" -ne 0 ]; then
    die "backup finished with ${failures} failed source(s)"
fi

log "backup complete — snapshot=${SNAPSHOT}"
