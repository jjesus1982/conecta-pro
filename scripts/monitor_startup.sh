#!/bin/bash
# ═══════════════════════════════════════════════
# Monitor Startup — Conecta PRO
# Executado via @reboot cron (sleep 90 primeiro)
# Aguarda: rede → Docker → backend
# ═══════════════════════════════════════════════

BOT_TOKEN="${MONITOR_BOT_TOKEN:-}"  # pragma: allowlist secret
CHAT_ID="${MONITOR_CHAT_ID:-5536961034}"
STARTUP_LOG="/opt/conecta-pro/logs/startup.log"
HORA=$(date '+%d/%m/%Y %H:%M')

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$STARTUP_LOG"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

telegram() {
    curl -sf -X POST \
        "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -H "Content-Type: application/json" \
        -d "{\"chat_id\":\"${CHAT_ID}\",\"text\":\"$1\",\"parse_mode\":\"HTML\"}" \
        > /dev/null 2>&1
}

log "=== Monitor Startup iniciando ==="

# ── PASSO 1: Aguardar rede ─────────────────────
log "Aguardando rede..."
NET_OK=0
for i in $(seq 1 30); do
    if ping -c1 -W2 8.8.8.8 > /dev/null 2>&1; then
        NET_OK=1
        log "Rede disponível (tentativa $i)"
        break
    fi
    sleep 5
done

if [ "$NET_OK" = "0" ]; then
    log "ERRO: Rede não disponível após 150s"
    telegram "⚠️ <b>MONITOR STARTUP — ALERTA</b>%0A%0A🌐 Rede indisponível após reboot%0A⏰ $HORA%0A%0A❌ Monitor não pôde iniciar"
    exit 1
fi

# ── PASSO 2: Aguardar Docker ───────────────────
log "Aguardando Docker..."
DOCKER_OK=0
for i in $(seq 1 24); do
    if docker info > /dev/null 2>&1; then
        DOCKER_OK=1
        log "Docker disponível (tentativa $i)"
        break
    fi
    sleep 5
done

if [ "$DOCKER_OK" = "0" ]; then
    log "ERRO: Docker não disponível após 120s"
    telegram "⚠️ <b>MONITOR STARTUP — ALERTA</b>%0A%0A🐳 Docker indisponível após reboot%0A⏰ $HORA%0A%0A❌ Monitor não pôde iniciar"
    exit 1
fi

# ── PASSO 3: Aguardar backend ──────────────────
log "Aguardando backend (127.0.0.1:8080)..."
BACKEND_OK=0
for i in $(seq 1 36); do
    CODE=$(curl -sf -o /dev/null -w "%{http_code}" \
        http://127.0.0.1:8080/health 2>/dev/null || echo "0")
    if [ "$CODE" = "200" ]; then
        BACKEND_OK=1
        log "Backend disponível após ${i}x10s"
        break
    fi
    sleep 10
done

if [ "$BACKEND_OK" = "0" ]; then
    log "AVISO: Backend não respondeu em 360s — continuando mesmo assim"
    telegram "⚠️ <b>MONITOR STARTUP — AVISO</b>%0A%0A🔧 Backend lento após reboot%0A⏰ $HORA%0AMonitor iniciando mesmo assim..."
fi

# ── PASSO 4: Notificar Jordan ──────────────────
UPTIME=$(uptime -p 2>/dev/null | sed 's/up //' || echo "N/A")
CONTAINERS=$(docker ps --format '{{.Names}}' 2>/dev/null | wc -l || echo "?")
BACKEND_LINHA="$([ "$BACKEND_OK" = "1" ] && echo "✅ Backend: Online" || echo "⚠️ Backend: Lento")"

MSG="🟢 <b>MONITOR ONLINE — REBOOT DETECTADO</b>
━━━━━━━━━━━━━━━━━━━
⏰ <b>$HORA</b>

✅ Rede: OK
✅ Docker: OK
$BACKEND_LINHA

🐳 Containers ativos: $CONTAINERS
⏱️ Uptime: $UPTIME

🔄 Iniciando primeiro ciclo de auditoria..."

telegram "$MSG"
log "Notificação de startup enviada ao Telegram"

# ── PASSO 5: Primeiro ciclo de auditoria ──────
log "Executando primeiro ciclo de auditoria..."
MONITOR_BOT_TOKEN="$BOT_TOKEN" \
MONITOR_CHAT_ID="$CHAT_ID" \
/usr/bin/python3 /opt/conecta-pro/agents/skills_agent.py \
    >> "$STARTUP_LOG" 2>&1

EXIT_CODE=$?
if [ "$EXIT_CODE" = "0" ]; then
    log "Primeiro ciclo concluído com sucesso"
else
    log "AVISO: Primeiro ciclo terminou com código $EXIT_CODE"
fi

log "=== Monitor Startup finalizado ==="
