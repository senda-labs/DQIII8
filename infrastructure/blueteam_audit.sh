#!/bin/bash
# Blue-team periodic audit — read-only, no mutations.
# Logs to /var/log/blueteam-audit.log. Run manually first; only cron after review.
set -uo pipefail

LOG=/var/log/blueteam-audit.log
{
  echo "==================== $(date -Is) ===================="

  echo "--- CrowdSec active decisions ---"
  cscli decisions list 2>&1

  echo "--- UFW status ---"
  ufw status verbose 2>&1

  echo "--- sshd_config drift check (sha256) ---"
  sha256sum /etc/ssh/sshd_config 2>&1

  echo "--- Failed SSH auth attempts (last 24h) ---"
  journalctl -u ssh.service --since "24 hours ago" 2>&1 | grep -iE "failed|invalid" | tail -30

  echo "--- Listening ports ---"
  ss -tlnp 2>&1

  echo "--- AIDE last check summary (if run today) ---"
  tail -5 /var/log/aide/aide.log 2>/dev/null || echo "(no aide.log yet)"

  echo "--- rkhunter last warnings ---"
  grep -i "warning" /var/log/rkhunter.log 2>/dev/null | tail -10

} >> "$LOG" 2>&1

echo "Audit appended to $LOG"
