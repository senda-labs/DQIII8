#!/usr/bin/env bash
# Run this on Hostinger (where hostkey-pg-scratch actually runs, port 15432).
# Installs the DOCKER-USER firewall rule blocking external access to the
# exposed 0.0.0.0:15432 Postgres port, mirroring the existing 5432 mitigation
# (docker-user-block-5432.service). See infrastructure/systemd/docker-user-block-15432.service.
set -euo pipefail

SRC=/root/dqiii8/infrastructure/systemd/docker-user-block-15432.service
DEST=/etc/systemd/system/docker-user-block-15432.service

cp "$SRC" "$DEST"
systemctl daemon-reload
systemctl enable --now docker-user-block-15432.service
systemctl status docker-user-block-15432.service --no-pager

echo
echo "Verificando regla en DOCKER-USER:"
iptables -L DOCKER-USER -n --line-numbers | grep 15432
