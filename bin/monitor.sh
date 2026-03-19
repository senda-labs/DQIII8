#!/usr/bin/env bash
# DQIII8 system monitor — escribe métricas cada 30s a system_metrics.log
LOG=/root/jarvis/database/system_metrics.log

while true; do
    TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    RAM=$(free -m | awk '/^Mem/{printf "used=%dMB total=%dMB pct=%d%%", $3, $2, int($3/$2*100)}')
    SWAP=$(free -m | awk '/^Swap/{printf "used=%dMB total=%dMB", $3, $2}')
    CPU=$(top -bn1 | awk '/^%Cpu/{printf "usr=%.1f%% sys=%.1f%% idle=%.1f%%", $2, $4, $8}')
    echo "${TIMESTAMP} | RAM: ${RAM} | SWAP: ${SWAP} | CPU: ${CPU}" >> "$LOG"
    sleep 30
done
