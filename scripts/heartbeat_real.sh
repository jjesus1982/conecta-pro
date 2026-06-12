#!/bin/bash
# Heartbeat REAL — dados crus do sistema, sem IA, sem predição. [FASE2-JL 20260612]
# Envia a cada 6h pro Telegram (mesmo bot das demais notificações reais).
set -u
TOKEN="${TELEGRAM_BOT_TOKEN:-${MONITOR_BOT_TOKEN:-}}"
CHAT="${TELEGRAM_CHAT_ID:-${MONITOR_CHAT_ID:-}}"
[ -z "$TOKEN" ] || [ -z "$CHAT" ] && exit 0

CPU=$(awk '{print $1}' /proc/loadavg)
NPROC=$(nproc)
MEM=$(free -m | awk '/^Mem:/{printf "%.0f%% (%dMB livres)", $3*100/$2, $7}')
DISK=$(df -h / | awk 'NR==2{print $5" usado ("$4" livres)"}')
UP=$(awk '{printf "%.1f dias", $1/86400}' /proc/uptime)
TOTAL=$(docker ps -q 2>/dev/null | wc -l)
UNHEALTHY=$(docker ps --format '{{.Names}} {{.Status}}' 2>/dev/null | grep -ciE 'unhealthy|Restarting' || true)
HEALTH=$(curl -sf -o /dev/null -w '%{http_code}' --max-time 10 http://localhost:8080/health 2>/dev/null || echo "FALHOU")
FRONT=$(curl -sf -o /dev/null -w '%{http_code}' --max-time 10 http://localhost:3001/ 2>/dev/null || echo "FALHOU")

STATUS="✅"
[ "$HEALTH" != "200" ] || [ "$FRONT" != "200" ] || [ "$UNHEALTHY" -gt 0 ] && STATUS="⚠️"

MSG="$STATUS <b>Heartbeat Conecta PRO</b> (dados reais)
🖥 CPU load: ${CPU}/${NPROC} | RAM: ${MEM}
💾 Disco /: ${DISK} | Uptime: ${UP}
🐳 Containers up: ${TOTAL} | unhealthy: ${UNHEALTHY}
🌐 Backend /health: ${HEALTH} | Frontend: ${FRONT}"

curl -sf -X POST "https://api.telegram.org/bot${TOKEN}/sendMessage" \
  -d chat_id="${CHAT}" -d parse_mode="HTML" --data-urlencode text="${MSG}" >/dev/null 2>&1
exit 0
