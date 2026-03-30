#!/usr/bin/env bash
# launch_beeswarm.sh — BeeSwarm layout: Sonnet planner + 3 Haiku workers + Yazi
# Usage: bash bin/workspace/launch_beeswarm.sh [session-name]
set -euo pipefail

SESSION="${1:-dqiii8-beeswarm}"
DQIII8="/root/dqiii8"

tmux kill-session -t "$SESSION" 2>/dev/null || true

# Main session: split into left (planner) and right column
tmux new-session -d -s "$SESSION" -x 220 -y 55 -c "$DQIII8"

# Right column (40%)
tmux split-window -h -p 40 -t "$SESSION":0 -c "$DQIII8"

# Left side: split into top (planner) and bottom (Yazi)
tmux split-window -v -p 25 -t "$SESSION":0.0 -c "$DQIII8"

# Right column: 3 worker panels
tmux split-window -v -p 66 -t "$SESSION":0.2 -c "$DQIII8"
tmux split-window -v -p 50 -t "$SESSION":0.3 -c "$DQIII8"

# Panel 0 (left top, large): Sonnet planner
tmux send-keys -t "$SESSION":0.0 "echo '🧠 Planner (Sonnet) — lanza: claude o python3 bin/bee_swarm.py'" Enter

# Panel 1 (left bottom): Yazi on dqiii8 root — watch file changes
tmux send-keys -t "$SESSION":0.1 "yazi $DQIII8" Enter

# Panel 2 (right top): Worker 1 (Haiku)
tmux send-keys -t "$SESSION":0.2 "echo '🐝 Worker 1 (Haiku) — claude --model claude-haiku-4-5-20251001 -p'" Enter

# Panel 3 (right middle): Worker 2 (Haiku)
tmux send-keys -t "$SESSION":0.3 "echo '🐝 Worker 2 (Haiku) — claude --model claude-haiku-4-5-20251001 -p'" Enter

# Panel 4 (right bottom): Worker 3 (Haiku)
tmux send-keys -t "$SESSION":0.4 "echo '🐝 Worker 3 (Haiku) — claude --model claude-haiku-4-5-20251001 -p'" Enter

tmux select-pane -t "$SESSION":0.0

echo "✓ BeeSwarm session '$SESSION' launched. Attach with: tmux attach -t $SESSION"
tmux attach -t "$SESSION"
