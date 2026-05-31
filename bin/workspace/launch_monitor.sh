#!/usr/bin/env bash
# launch_monitor.sh — Monitoring layout: tokens + logs + Yazi + tests
# Usage: bash bin/workspace/launch_monitor.sh [session-name] [project-path]
set -euo pipefail

SESSION="${1:-dqiii8-monitor}"
DQIII8="${DQIII8_ROOT:-/root/dqiii8}"
PROJECT="${2:-$DQIII8}"

tmux kill-session -t "$SESSION" 2>/dev/null || true

# 2x2 grid layout
tmux new-session -d -s "$SESSION" -x 220 -y 55 -c "$DQIII8"

# Split into left and right columns
tmux split-window -h -p 50 -t "$SESSION":0 -c "$DQIII8"

# Split each column into 2 rows
tmux split-window -v -p 50 -t "$SESSION":0.0 -c "$DQIII8"
tmux split-window -v -p 50 -t "$SESSION":0.2 -c "$DQIII8"

# Panel 0 (top-left): Token usage
tmux send-keys -t "$SESSION":0.0 "watch -n 10 'cd $DQIII8 && python3 -c \"from bin.core.db import get_db; import sqlite3; db=sqlite3.connect(\\\"database/dqiii8_metrics.db\\\"); r=db.execute(\\\"SELECT model,SUM(input_tokens+output_tokens) FROM token_usage GROUP BY model ORDER BY 2 DESC LIMIT 8\\\").fetchall(); [print(f\\\"{m}: {t:,}\\\") for m,t in r]\" 2>/dev/null || echo No token data yet'" Enter

# Panel 1 (bottom-left): Bot logs live
tmux send-keys -t "$SESSION":0.1 "journalctl -u dqiii8-bot -f --no-pager 2>/dev/null || echo 'dqiii8-bot inactive'" Enter

# Panel 2 (top-right): Yazi on active project
tmux send-keys -t "$SESSION":0.2 "yazi $PROJECT" Enter

# Panel 3 (bottom-right): Continuous test runner
tmux send-keys -t "$SESSION":0.3 "watch -n 30 'cd $DQIII8 && python3 -m pytest tests/test_smoke.py -q 2>&1 | tail -5'" Enter

tmux select-pane -t "$SESSION":0.2

echo "✓ Monitor session '$SESSION' launched. Attach with: tmux attach -t $SESSION"
tmux attach -t "$SESSION"
