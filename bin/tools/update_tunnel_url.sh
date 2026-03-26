#!/bin/bash
# Reads the active trycloudflare URL from the cloudflared-autoreporte journal
# and updates WEBHOOK_URL in the auto-report .env.
# Called as ExecStartPost in cloudflared-autoreporte.service.

ENV_FILE="/root/dqiii8/my-projects/auto-report/.env"

NEW_URL=$(journalctl -u cloudflared-autoreporte --no-pager -n 50 2>/dev/null \
    | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' \
    | tail -1)

if [ -z "$NEW_URL" ]; then
    echo "[update_tunnel_url] WARNING: no trycloudflare URL found in journal" >&2
    exit 0
fi

if grep -q "^WEBHOOK_URL=" "$ENV_FILE" 2>/dev/null; then
    sed -i "s|^WEBHOOK_URL=.*|WEBHOOK_URL=$NEW_URL|" "$ENV_FILE"
else
    echo "WEBHOOK_URL=$NEW_URL" >> "$ENV_FILE"
fi

echo "[update_tunnel_url] WEBHOOK_URL updated to $NEW_URL"
