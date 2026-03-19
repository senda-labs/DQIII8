#!/bin/bash
# DQIII8 — Autonomous Loop
# Launches claude in autonomous mode with 3-layer supervisor active.
# Usage: autonomous_loop.sh 'objective' [max_hours]
#
# The supervisor intercepts tools via hooks:
#   Layer 1: READ_PREFIXES → auto-approve without LLM
#   Layer 2: LLM supervisor (openrouter, 3s timeout → ALLOW)
#   Layer 3: CRITICAL_PATTERNS → Telegram escalation (10min → deny)

set -euo pipefail

export JARVIS_MODE=autonomous
export JARVIS_ROOT=/root/jarvis

OBJECTIVE="${1:-}"
MAX_HOURS="${2:-8}"

if [ -z "$OBJECTIVE" ]; then
    echo "Usage: autonomous_loop.sh 'objective' [max_hours]"
    echo "Example: autonomous_loop.sh 'Audit system and fix errors' 4"
    exit 1
fi

JARVIS_ROOT_PATH="/root/jarvis"
OBJECTIVE_FILE="$JARVIS_ROOT_PATH/tasks/current_objective.txt"
WATCHDOG_PID_FILE="/tmp/jarvis_watchdog.pid"
STOP_FLAG="$JARVIS_ROOT_PATH/tasks/.stop_flag"

echo "🌙 DQIII8 Autonomous Mode — Supervisor: ACTIVE"
echo "   Objective: $OBJECTIVE"
echo "   Max hours: $MAX_HOURS"
echo "   Mode     : JARVIS_MODE=autonomous (hooks 3-layer active)"
echo ""

# Write objective for Layer 2 (LLM supervisor reads this file)
printf '%s\nStarted: %s\n' "$OBJECTIVE" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$OBJECTIVE_FILE"

# Launch watchdog in background
python3 "$JARVIS_ROOT_PATH/bin/autonomous_watchdog.py" &
WATCHDOG_PID=$!
echo $WATCHDOG_PID > "$WATCHDOG_PID_FILE"
echo "   Watchdog PID: $WATCHDOG_PID"
echo ""

# Cleanup on exit (CTRL-C, timeout, etc.)
cleanup() {
    echo ""
    echo "🧹 Cleaning up autonomous session..."
    kill "$(cat "$WATCHDOG_PID_FILE" 2>/dev/null)" 2>/dev/null || true
    rm -f "$WATCHDOG_PID_FILE" "$OBJECTIVE_FILE"
    echo "✅ Autonomous session completed"
}
trap cleanup EXIT

cd "$JARVIS_ROOT_PATH"

# Ensure results directory exists
mkdir -p "$JARVIS_ROOT_PATH/tasks/results"

# Calculate timeout in seconds
MAX_SECONDS=$(( MAX_HOURS * 3600 ))

# Check stop flag before starting
if [ -f "$STOP_FLAG" ]; then
    echo "Stop flag detected — aborting before start."
    rm -f "$STOP_FLAG"
    exit 0
fi

# Clear stop flag from previous sessions (watchdog leaves it between runs)
rm -f /tmp/jarvis_autonomous_stop.flag

# Launch claude with time limit
# < /dev/null: in detached tmux, stdin is a PTY that does not send EOF;
#   claude -p could block reading stdin. /dev/null gives immediate EOF.
timeout "$MAX_SECONDS" claude \
    --add-dir /root/jarvis \
    -p "$OBJECTIVE" \
    < /dev/null \
    || EXIT_CODE=$?

# timeout returns 124 if the limit is reached
if [ "${EXIT_CODE:-0}" -eq 124 ]; then
    echo ""
    echo "⏰ Maximum time ($MAX_HOURS h) reached — session terminated automatically"
fi
