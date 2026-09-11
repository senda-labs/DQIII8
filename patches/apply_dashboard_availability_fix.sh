#!/bin/bash
# Root-cause fix for the 2026-09-04 dq-dashboard.service ~3h35min outage.
# Ejecutar a mano como root, fuera de una sesion de Claude Code:
# /etc/systemd/ es blocked-path para un agente, sin excepcion posible.
#
# Idempotente: se puede ejecutar N veces, el resultado final es el mismo
# (cada fichero se sobreescribe entero, nunca se parchea incrementalmente).
#
# Causa raiz 1 (disparador ese dia): puerto 8080 ya ocupado al arrancar
#   (instancia manual de dashboard.py dejada corriendo, colisiona con el
#   arranque via systemd).
# Causa raiz 2 (por que se quedo caido 3h35min): StartLimitBurst=5 en
#   StartLimitIntervalSec=600 hace que systemd abandone los reintentos para
#   siempre tras 5 fallos en <10min, sin auto-recuperacion. Confirmado via
#   journalctl: 5 fallos en <1 minuto, luego 3h35min sin ningun intento mas
#   hasta un restart manual a las 20:15:59.
set -euo pipefail

UNIT_DIR="/etc/systemd/system/dq-dashboard.service.d"
DASH_UNIT="dq-dashboard.service"
ENV_FILE="/root/dqiii8/.env"

echo "[1/6] Verificando pre-condiciones..."
if ! systemctl list-unit-files "$DASH_UNIT" >/dev/null 2>&1; then
  echo "ERROR: $DASH_UNIT no existe en este host. Abortando." >&2
  exit 1
fi
if [ ! -f /root/dqiii8/bin/monitoring/dq_dashboard_selfheal.py ]; then
  echo "ERROR: falta bin/monitoring/dq_dashboard_selfheal.py (deberia venir del repo)." >&2
  exit 1
fi
if [ ! -f "$ENV_FILE" ]; then
  echo "AVISO: $ENV_FILE no existe en esa ruta; ajusta EnvironmentFile= abajo si tu .env vive en otro sitio." >&2
fi

echo "[2/6] Escribiendo fix 1/2: liberar el puerto 8080 antes de arrancar..."
mkdir -p "$UNIT_DIR"
cat > "$UNIT_DIR/hardening.conf" <<EOF
[Unit]
OnFailure=dqiii8-alert@%n
StartLimitIntervalSec=600
StartLimitBurst=5

[Service]
MemoryMax=2G
CPUQuota=80%
TasksMax=200
ExecStartPre=/usr/bin/fuser -k -TERM 8080/tcp
SuccessExitStatus=0 1
EOF
# SuccessExitStatus=0 1: fuser -k devuelve 1 (no error) cuando no habia nada
# que matar, el caso normal. Sin esto, ExecStartPre "fallaria" cada arranque
# limpio y bloquearia el servicio -- verificado (fuser -k contra puerto
# libre = exit 1).

echo "[3/6] Escribiendo fix 2/2: timer de self-heal cada 2 min..."
cat > /etc/systemd/system/dq-dashboard-selfheal.service <<EOF
[Unit]
Description=DQIII8 dashboard self-heal (detect start-limit-hit, reset+restart)

[Service]
Type=oneshot
User=root
WorkingDirectory=/root/dqiii8
EnvironmentFile=$ENV_FILE
ExecStart=/usr/bin/python3 bin/monitoring/dq_dashboard_selfheal.py
EOF

cat > /etc/systemd/system/dq-dashboard-selfheal.timer <<EOF
[Unit]
Description=Run dq-dashboard self-heal every 2 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=2min

[Install]
WantedBy=timers.target
EOF

echo "[4/6] Verificando sintaxis antes de recargar systemd..."
# Un drop-in .conf no es verificable como fichero suelto (systemd-analyze
# verify lo rechaza con "Invalid argument", confirmado en pruebas); se
# verifica por nombre de unidad, que resuelve el .d/ automaticamente.
systemd-analyze verify "$DASH_UNIT"
systemd-analyze verify /etc/systemd/system/dq-dashboard-selfheal.service
systemd-analyze verify /etc/systemd/system/dq-dashboard-selfheal.timer

echo "[5/6] Aplicando (daemon-reload + enable --now, ambos idempotentes)..."
systemctl daemon-reload
systemctl enable --now dq-dashboard-selfheal.timer

echo "[6/6] Verificacion post-aplicacion..."
echo "--- estado del dashboard (no deberia haber cambiado) ---"
systemctl is-active "$DASH_UNIT"
echo "--- timer instalado y activo ---"
systemctl is-active dq-dashboard-selfheal.timer
systemctl list-timers dq-dashboard-selfheal.timer --no-pager
echo "--- ejecucion manual del self-heal contra el servicio SANO (debe ser no-op, sin notificar) ---"
python3 /root/dqiii8/bin/monitoring/dq_dashboard_selfheal.py && echo "OK: no-op confirmado (exit 0, servicio ya estaba activo)"

echo ""
echo "Aplicado. Re-test supervisado OPCIONAL para confirmar la auto-recuperacion en vivo"
echo "(rompe el dashboard a proposito, solo si quieres verlo en accion):"
echo "  1. systemctl stop $DASH_UNIT"
echo "  2. python3 -c \"import socket,time; s=socket.socket(); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); s.bind(('127.0.0.1',8080)); s.listen(1); time.sleep(150)\" &"
echo "  3. systemctl start $DASH_UNIT   # fallara y Restart=always agotara el burst en <1 min"
echo "  4. systemctl is-failed $DASH_UNIT   # deberia decir 'failed'"
echo "  5. Esperar hasta 2 min: systemctl is-active $DASH_UNIT   # deberia volver a 'active' solo"
echo "  6. Deberias recibir una notificacion de Telegram del self-heal"
