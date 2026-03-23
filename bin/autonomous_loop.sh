#!/bin/bash
# DQIII8 — Autonomous Loop
# Launches claude in cycles, reporting each to Telegram via bin/core/notify.py
# Usage: autonomous_loop.sh 'objective' [max_hours] [max_iter]
#
# The supervisor intercepts tools via hooks:
#   Layer 1: READ_PREFIXES → auto-approve without LLM
#   Layer 2: LLM supervisor (openrouter, 3s timeout → ALLOW)
#   Layer 3: CRITICAL_PATTERNS → Telegram escalation (10min → deny)

set -euo pipefail

export JARVIS_MODE=autonomous
export JARVIS_ROOT=/root/jarvis

# Prevent CLAUDE_CODE_OAUTH_TOKEN from overriding ~/.claude/.credentials.json
# Claude Code uses credentials.json with auto-renewal — env var breaks auth
unset CLAUDE_CODE_OAUTH_TOKEN

OBJECTIVE="${1:-}"
MAX_HOURS="${2:-8}"
MAX_ITER="${3:-100}"  # Maximum claude invocations per session (safety cap)

if [ -z "$OBJECTIVE" ]; then
    echo "Usage: autonomous_loop.sh 'objective' [max_hours] [max_iter]"
    echo "Example: autonomous_loop.sh 'Audit system and fix errors' 4"
    exit 1
fi

JARVIS_ROOT_PATH="/root/jarvis"
NOTIFY="python3 $JARVIS_ROOT_PATH/bin/core/notify.py"
OBJECTIVE_FILE="$JARVIS_ROOT_PATH/tasks/current_objective.txt"
WATCHDOG_PID_FILE="/tmp/jarvis_watchdog.pid"
STOP_FLAG="$JARVIS_ROOT_PATH/tasks/.stop_flag"

echo "DQIII8 Autonomous Mode — Supervisor: ACTIVE"
echo "   Objective: $OBJECTIVE"
echo "   Max hours: $MAX_HOURS"
echo "   Max iter : $MAX_ITER"
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

# Cleanup on exit (CTRL-C, timeout, natural end)
cleanup() {
    echo ""
    echo "Cleaning up autonomous session..."
    kill "$(cat "$WATCHDOG_PID_FILE" 2>/dev/null)" 2>/dev/null || true
    rm -f "$WATCHDOG_PID_FILE" "$OBJECTIVE_FILE"
    $NOTIFY "[DQIII8] Loop finalizado. Ciclos: ${CYCLE:-0}. Objetivo: ${OBJECTIVE:0:80}" || true
    echo "Autonomous session completed"
}
trap cleanup EXIT

cd "$JARVIS_ROOT_PATH"
mkdir -p "$JARVIS_ROOT_PATH/tasks/results"

# Calculate timeout in seconds
MAX_SECONDS=$(( MAX_HOURS * 3600 ))
START_TIME=$(date +%s)
CYCLE=0

# Check stop flag before starting
if [ -f "$STOP_FLAG" ]; then
    echo "Stop flag detected — aborting before start."
    rm -f "$STOP_FLAG"
    exit 0
fi
rm -f /tmp/jarvis_autonomous_stop.flag

# Notify loop start
$NOTIFY "[DQIII8] Loop iniciado — ${OBJECTIVE:0:80} (${MAX_HOURS}h / ${MAX_ITER} iter)" || true

# ── Main loop ─────────────────────────────────────────────────────────────────

while true; do
    CYCLE=$(( CYCLE + 1 ))
    ELAPSED=$(( $(date +%s) - START_TIME ))

    # Time limit check
    if [ "$ELAPSED" -ge "$MAX_SECONDS" ]; then
        echo "Maximum time (${MAX_HOURS}h) reached."
        $NOTIFY "[DQIII8] Tiempo agotado (${MAX_HOURS}h). Ciclos: $CYCLE." || true
        break
    fi

    # Iteration limit check
    if [ "$CYCLE" -gt "$MAX_ITER" ]; then
        echo "Max iterations ($MAX_ITER) reached."
        $NOTIFY "[DQIII8] Limite iteraciones ($MAX_ITER) alcanzado." || true
        break
    fi

    # Stop flag check
    if [ -f "$STOP_FLAG" ]; then
        echo "Stop flag detected — exiting loop."
        $NOTIFY "[DQIII8] Stop flag detectado. Loop pausado manualmente." || true
        rm -f "$STOP_FLAG"
        break
    fi

    echo "--- Cycle $CYCLE / $MAX_ITER ---"
    $NOTIFY "[DQIII8] Ciclo $CYCLE/$MAX_ITER — ${OBJECTIVE:0:80}" || true

    # Run claude, tee output to terminal + temp file for error detection
    ERR_FILE=$(mktemp /tmp/jarvis_err_XXXXXX.txt)
    EXIT_CODE=0
    REMAINING=$(( MAX_SECONDS - ELAPSED ))

    timeout "$REMAINING" claude \
        --add-dir /root/jarvis \
        -p "$OBJECTIVE" \
        < /dev/null \
        2>"$ERR_FILE" \
        || EXIT_CODE=$?

    ERR_TEXT=$(cat "$ERR_FILE" | tr '\n' ' ' | cut -c1-200)
    rm -f "$ERR_FILE"

    # ── Auth failure ─────────────────────────────────────────────────────────
    if echo "$ERR_TEXT" | grep -qiE "401|unauthorized|credentials.*expired|auth.*fail|login.required|oauth"; then
        echo "Auth failure detected."
        $NOTIFY "[DQIII8] Auth expirado. Ejecuta: claude /login en tmux jarvis" || true

        AUTH_RETRY=0
        while true; do
            sleep 300  # wait 5 min before retry
            AUTH_RETRY=$(( AUTH_RETRY + 1 ))
            # Minimal auth probe
            if timeout 30 claude -p "ok" --output-format json < /dev/null 2>/dev/null \
                    | grep -q '"result"'; then
                $NOTIFY "[DQIII8] Auth restaurado. Reanudando loop." || true
                break
            fi
            if [ "$AUTH_RETRY" -ge 12 ]; then  # 1 hour max wait
                $NOTIFY "[DQIII8] Auth no restaurado tras 1h. Abortando loop." || true
                exit 1
            fi
            $NOTIFY "[DQIII8] Auth sigue caido. Reintento ${AUTH_RETRY}/12..." || true
        done
        continue  # retry cycle after auth restored
    fi

    # ── Timeout ──────────────────────────────────────────────────────────────
    if [ "$EXIT_CODE" -eq 124 ]; then
        echo "Cycle $CYCLE timed out."
        $NOTIFY "[DQIII8] Ciclo $CYCLE: timeout. Continuando." || true
        break  # overall time budget exhausted, exit loop
    fi

    # ── Other errors ─────────────────────────────────────────────────────────
    if [ "$EXIT_CODE" -ne 0 ]; then
        echo "Cycle $CYCLE exited with code $EXIT_CODE."
        $NOTIFY "[DQIII8] Ciclo $CYCLE error (exit ${EXIT_CODE}). ${ERR_TEXT:0:100}" || true
        continue  # continue to next cycle, user intervenes manually if needed
    fi

    # ── Success ───────────────────────────────────────────────────────────────
    echo "Cycle $CYCLE completed OK."
    $NOTIFY "[DQIII8] Ciclo $CYCLE OK. Objetivo completado." || true
    break  # single-objective mode: success → stop
done
