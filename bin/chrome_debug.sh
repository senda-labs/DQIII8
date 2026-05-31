#!/usr/bin/env bash
# chrome_debug.sh — lanza Chrome con CDP en puerto 9222 (headless, sin interfere con pipeline)
# Uso en VPS:  bash ~/dqiii8/bin/chrome_debug.sh
# Uso remoto:  ssh root@YOUR_VPS_HOST 'bash ~/dqiii8/bin/chrome_debug.sh'

PORT=9222
LOG=/tmp/chrome_debug.log
PID_FILE=/tmp/chrome_debug.pid

# Matar instancia anterior en ese puerto
if [[ -f "$PID_FILE" ]]; then
    OLD_PID=$(cat "$PID_FILE")
    kill "$OLD_PID" 2>/dev/null && echo "[chrome] killed old instance (pid=$OLD_PID)"
    rm -f "$PID_FILE"
fi
pkill -f "remote-debugging-port=$PORT" 2>/dev/null || true
sleep 0.5

# Lanzar Chrome headless con CDP
google-chrome \
    --remote-debugging-port=$PORT \
    --headless=new \
    --no-sandbox \
    --disable-gpu \
    --disable-dev-shm-usage \
    --user-data-dir=/tmp/chrome_debug_profile \
    --no-first-run \
    --no-default-browser-check \
    >/tmp/chrome_debug.log 2>&1 &

echo $! > "$PID_FILE"
echo "[chrome] started (pid=$!, port=$PORT)"

# Verificar que levantó (máx 5s)
for i in 1 2 3 4 5; do
    sleep 1
    RESP=$(curl -sf "http://localhost:$PORT/json/version" 2>/dev/null)
    if [[ -n "$RESP" ]]; then
        BROWSER=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('Browser','?'))" 2>/dev/null)
        echo "[chrome] OK — $BROWSER @ localhost:$PORT"
        exit 0
    fi
done

echo "[chrome] ERROR — no responde en $PORT. Ver $LOG"
exit 1
