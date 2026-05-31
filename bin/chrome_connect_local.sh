#!/usr/bin/env bash
# chrome_connect_local.sh — EJECUTAR EN TU PC LOCAL (no en el VPS)
# Conecta Chrome remoto del VPS via SSH tunnel en un comando.
#
# Requisitos local: ssh configurado, curl disponible
# Uso: bash chrome_connect_local.sh
# Añadir alias en ~/.zshrc o ~/.bashrc:
#   alias chrome-vps='bash ~/chrome_connect_local.sh'

VPS_HOST="${DQIII8_VPS_HOST:-root@your-vps-host}"
REMOTE_PORT=9222
LOCAL_PORT=9222
TUNNEL_PID_FILE="/tmp/chrome_tunnel.pid"

# 1. Matar túnel anterior si existe
if [[ -f "$TUNNEL_PID_FILE" ]]; then
    OLD=$(cat "$TUNNEL_PID_FILE")
    kill "$OLD" 2>/dev/null && echo "[tunnel] killed old tunnel (pid=$OLD)"
    rm -f "$TUNNEL_PID_FILE"
fi

# 2. Lanzar Chrome headless en el VPS
echo "[vps] iniciando Chrome remoto..."
ssh "$VPS_HOST" 'bash ~/dqiii8/bin/chrome_debug.sh'
VPS_RC=$?
if [[ $VPS_RC -ne 0 ]]; then
    echo "[ERROR] Chrome no arrancó en el VPS"
    exit 1
fi

# 3. Abrir túnel SSH en background
echo "[tunnel] abriendo túnel localhost:$LOCAL_PORT → VPS:$REMOTE_PORT..."
ssh -fNL "${LOCAL_PORT}:localhost:${REMOTE_PORT}" "$VPS_HOST"
echo $! > "$TUNNEL_PID_FILE"   # nota: con -f el PID real es el hijo — usar pgrep si necesario
sleep 1

# 4. Verificar desde local
RESP=$(curl -sf "http://localhost:$LOCAL_PORT/json/version" 2>/dev/null)
if [[ -n "$RESP" ]]; then
    BROWSER=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('Browser','?'))" 2>/dev/null)
    echo ""
    echo "╔══════════════════════════════════════════╗"
    echo "║  Chrome CDP — OK                         ║"
    echo "║  $BROWSER"
    echo "║  URL local: http://localhost:$LOCAL_PORT    ║"
    echo "║  DevTools:  chrome://inspect             ║"
    echo "╚══════════════════════════════════════════╝"
    echo ""
    echo "Para cerrar el túnel: kill \$(pgrep -f 'ssh.*${LOCAL_PORT}:localhost')"
else
    echo "[ERROR] Túnel activo pero Chrome no responde en localhost:$LOCAL_PORT"
    exit 1
fi
