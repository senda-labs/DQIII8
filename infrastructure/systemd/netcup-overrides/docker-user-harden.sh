#!/bin/bash
# Ejecutar INMEDIATAMENTE tras instalar Docker en netcup-rs4000, ANTES de crear
# cualquier contenedor con -p. Docker inyecta reglas en DOCKER-USER que
# bypassan el "deny incoming" por defecto de UFW para puertos publicados.
#
# Efecto: fuerza que DOCKER-USER respete el mismo allowlist que UFW ya aplica
# (SSH del server viejo + rate-limit), en vez de aceptar todo el tráfico hacia
# contenedores publicados. Idempotente — seguro de re-ejecutar.
#
# BUG REAL encontrado y corregido 2026-09-07 (verificación end-to-end en
# netcup-rs4000, no hipotética): Docker crea DOCKER-USER con un RETURN
# incondicional como última regla por defecto. Un `-A ... DROP` simple queda
# DESPUÉS de ese RETURN — nunca se alcanza, regla muerta, el hardening no
# hacía nada pese a "verificarse" con `iptables -L` mostrando el DROP presente
# (presente ≠ alcanzable). Fix: el DROP se inserta ANTES del RETURN
# (posición dinámica, no hardcodeada), y solo si no hay ya un DROP en la
# cadena — así una segunda ejecución no duplica reglas.
set -euo pipefail

# Detecta backend (nftables en Debian 13 por defecto, ver CrowdSec bouncer)
if command -v nft >/dev/null && nft list tables 2>/dev/null | grep -q '^table ip docker'; then
  echo "Backend: nftables — aplicando reglas en tabla docker/DOCKER-USER"
  if ! nft list chain ip docker DOCKER-USER 2>/dev/null | grep -q ' drop$'; then
    # Docker crea su propia tabla 'docker' con chain DOCKER-USER en Debian 13.
    # Insertamos: permitir solo tráfico ya establecido/relacionado y loopback,
    # y bloquear el resto — mismo riesgo que la rama iptables: si Docker ya
    # tiene un `return` por defecto, debe insertarse ANTES, no añadirse
    # después (nft insert = al principio de la cadena, por eso el DROP va
    # primero en el orden de inserción para acabar último tras los ACCEPT).
    nft insert rule ip docker DOCKER-USER drop
    nft insert rule ip docker DOCKER-USER ct state established,related accept
    nft insert rule ip docker DOCKER-USER iif "lo" accept
  else
    echo "Ya hay una regla drop en DOCKER-USER — no se duplica."
  fi
else
  echo "Backend: iptables-legacy — aplicando reglas en DOCKER-USER"
  if ! iptables -L DOCKER-USER -n | grep -q '^DROP'; then
    iptables -I DOCKER-USER -m state --state ESTABLISHED,RELATED -j ACCEPT
    iptables -I DOCKER-USER -i lo -j ACCEPT
    # Inserta el DROP ANTES de la primera regla RETURN existente (el default
    # de Docker), no al final con -A — un RETURN incondicional antes del DROP
    # lo dejaría inalcanzable. Sin RETURN previo, cae al -A del final.
    return_line=$(iptables -L DOCKER-USER -n --line-numbers | awk '$2=="RETURN"{print $1; exit}')
    if [ -n "$return_line" ]; then
      iptables -I DOCKER-USER "$return_line" -j DROP
    else
      iptables -A DOCKER-USER -j DROP
    fi
  else
    echo "Ya hay una regla DROP en DOCKER-USER — no se duplica."
  fi
fi

echo "DOCKER-USER hardened. Verificar con: nft list ruleset | grep -A5 DOCKER-USER  (o iptables -L DOCKER-USER -n)"
echo "Cualquier contenedor publicado (-p) necesitará una regla explícita de origen permitido ANTES del DROP final."
