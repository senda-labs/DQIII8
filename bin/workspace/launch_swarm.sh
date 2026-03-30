#!/usr/bin/env bash
# launch_swarm.sh — Workspace principal: Claude Code + Yazi + logs + monitor
# Usage: bash bin/workspace/launch_swarm.sh [session-name]
set -euo pipefail

SESSION="${1:-dqiii8-swarm}"
DQIII8="/root/dqiii8"

# Kill existing session if present
tmux kill-session -t "$SESSION" 2>/dev/null || true

# Create new session, first window, main panel (starts in dqiii8 root)
tmux new-session -d -s "$SESSION" -x 220 -y 50 -c "$DQIII8"

# Split right (40% width) — right column
tmux split-window -h -p 40 -t "$SESSION":0 -c "$DQIII8"

# Split right column into 3 vertical panes
tmux split-window -v -p 66 -t "$SESSION":0.1 -c "$DQIII8"
tmux split-window -v -p 50 -t "$SESSION":0.2 -c "$DQIII8"

# Panel 0 (left, 60%): Claude Code session — just a shell ready to run cc
tmux send-keys -t "$SESSION":0.0 "echo '🤖 Panel principal — lanza: claude'" Enter

# Panel 1 (right top): Yazi file browser
tmux send-keys -t "$SESSION":0.1 "yazi $DQIII8" Enter

# Panel 2 (right middle): Bot logs live
tmux send-keys -t "$SESSION":0.2 "journalctl -u dqiii8-bot -f --no-pager 2>/dev/null || echo 'dqiii8-bot not running — tail /tmp/*.log'" Enter

# Panel 3 (right bottom): Resource monitor
if command -v htop &>/dev/null; then
    tmux send-keys -t "$SESSION":0.3 "htop" Enter
else
    tmux send-keys -t "$SESSION":0.3 "watch -n 2 'free -h && echo && uptime && echo && df -h /'" Enter
fi

# Focus main panel
tmux select-pane -t "$SESSION":0.0

echo "✓ Session '$SESSION' launched. Attach with: tmux attach -t $SESSION"
tmux attach -t "$SESSION"
