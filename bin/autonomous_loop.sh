#!/bin/bash
# JARVIS — Autonomous Loop
# Lanza claude en modo autónomo con supervisor 3-layer activo.
# Uso: autonomous_loop.sh 'objetivo' [horas_max]
#
# El supervisor intercepta herramientas via hooks:
#   Layer 1: READ_PREFIXES → auto-approve sin LLM
#   Layer 2: LLM supervisor (openrouter, 3s timeout → PERMITE)
#   Layer 3: CRITICAL_PATTERNS → Telegram escalation (10min → deny)

set -euo pipefail

export JARVIS_MODE=autonomous
export JARVIS_ROOT=/root/jarvis

OBJECTIVE="${1:-}"
MAX_HOURS="${2:-8}"

if [ -z "$OBJECTIVE" ]; then
    echo "Uso: autonomous_loop.sh 'objetivo' [horas_max]"
    echo "Ejemplo: autonomous_loop.sh 'Auditar sistema y corregir errores' 4"
    exit 1
fi

JARVIS_ROOT_PATH="/root/jarvis"
OBJECTIVE_FILE="$JARVIS_ROOT_PATH/tasks/current_objective.txt"
WATCHDOG_PID_FILE="/tmp/jarvis_watchdog.pid"
STOP_FLAG="$JARVIS_ROOT_PATH/tasks/.stop_flag"

echo "🌙 DQIII8 Autonomous Mode — Supervisor: ACTIVO"
echo "   Objetivo : $OBJECTIVE"
echo "   Max horas: $MAX_HOURS"
echo "   Modo     : JARVIS_MODE=autonomous (hooks 3-layer activos)"
echo ""

# Escribir objetivo para Layer 2 (LLM supervisor lee este archivo)
printf '%s\nStarted: %s\n' "$OBJECTIVE" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$OBJECTIVE_FILE"

# Lanzar watchdog en background
python3 "$JARVIS_ROOT_PATH/bin/autonomous_watchdog.py" &
WATCHDOG_PID=$!
echo $WATCHDOG_PID > "$WATCHDOG_PID_FILE"
echo "   Watchdog PID: $WATCHDOG_PID"
echo ""

# Cleanup en exit (CTRL-C, timeout, etc.)
cleanup() {
    echo ""
    echo "🧹 Limpiando sesión autónoma..."
    kill "$(cat "$WATCHDOG_PID_FILE" 2>/dev/null)" 2>/dev/null || true
    rm -f "$WATCHDOG_PID_FILE" "$OBJECTIVE_FILE"
    echo "✅ Autonomous session completed"
}
trap cleanup EXIT

cd "$JARVIS_ROOT_PATH"

# Asegurar directorio de resultados
mkdir -p "$JARVIS_ROOT_PATH/tasks/results"

# Calcular timeout en segundos
MAX_SECONDS=$(( MAX_HOURS * 3600 ))

# Verificar stop flag antes de iniciar
if [ -f "$STOP_FLAG" ]; then
    echo "Stop flag detectado — abortando antes de iniciar."
    rm -f "$STOP_FLAG"
    exit 0
fi

# Limpiar stop flag de sesiones anteriores (watchdog lo deja entre runs)
rm -f /tmp/jarvis_autonomous_stop.flag

# Lanzar claude con tiempo límite
# < /dev/null: en tmux detached, stdin es un PTY que no envía EOF;
#   claude -p podría bloquearse leyendo stdin. /dev/null da EOF inmediato.
timeout "$MAX_SECONDS" claude \
    --add-dir /root/jarvis \
    --add-dir /root/content-automation-faceless \
    -p "$OBJECTIVE" \
    < /dev/null \
    || EXIT_CODE=$?

# timeout devuelve 124 si alcanza el límite
if [ "${EXIT_CODE:-0}" -eq 124 ]; then
    echo ""
    echo "⏰ Tiempo máximo ($MAX_HOURS h) alcanzado — sesión terminada automáticamente"
fi
