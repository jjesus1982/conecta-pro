#!/bin/bash
# Sobe o display virtual + VNC + noVNC ANTES do app (robusto, sem race/lock).
set -e
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null || true
export DISPLAY=:99

Xvfb :99 -screen 0 1440x900x24 -ac &
sleep 3
fluxbox >/dev/null 2>&1 &
x11vnc -display :99 -forever -shared -nopw -rfbport 5900 -bg >/dev/null 2>&1 || true
sleep 1
websockify --web=/usr/share/novnc 6080 localhost:5900 >/dev/null 2>&1 &
sleep 2

echo "[entrypoint] display stack pronto (DISPLAY=:99), iniciando robô…"
exec python robot.py
