#!/usr/bin/env bash
# apply.sh — installs the Netcup-specific systemd overrides from this directory
# into /etc/systemd/system/ and reloads/restarts the affected services.
#
# Run manually by a human on Netcup (this directory's overrides target a path
# agent sessions cannot write to by design — see .claude/rules/02_hooks_and_permissions.md
# § Blocked paths). Safe to re-run any time these override files change.
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST=/etc/systemd/system

mkdir -p "${DEST}/dqiii8-bot.service.d" "${DEST}/dq-dashboard.service.d"
cp "${SRC}/dqiii8-bot.service.d/netcup-venv.conf" "${DEST}/dqiii8-bot.service.d/netcup-venv.conf"
cp "${SRC}/dq-dashboard.service.d/netcup-venv.conf" "${DEST}/dq-dashboard.service.d/netcup-venv.conf"

systemctl daemon-reload
systemctl restart dqiii8-bot dq-dashboard
sleep 2
systemctl is-active dqiii8-bot dq-dashboard
