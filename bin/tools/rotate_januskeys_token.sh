#!/usr/bin/env bash
# rotate_januskeys_token.sh — apply a rotated GitHub token to the januskeys-web
# remote and verify it works. Run as root on Hostinger, in your own terminal.
#
# Usage: bash rotate_januskeys_token.sh
# (no argument — it prompts for the token so you never have to paste a long
# single line that some terminals mangle on wrap)
set -euo pipefail

read -rsp "Paste the new GitHub token, then press Enter: " TOKEN
echo

if [ -z "$TOKEN" ]; then
    echo "No token entered — aborting." >&2
    exit 1
fi

REPO="/root/dqiii8/my-projects/website-fabric/sites/januskeys/web"

echo "[1/2] updating remote..."
git -C "$REPO" remote set-url origin "https://${TOKEN}@github.com/senda-labs/januskeys-web.git"

echo "[2/2] verifying..."
git -C "$REPO" ls-remote origin >/dev/null && echo "OK — remote reachable with the new token"
