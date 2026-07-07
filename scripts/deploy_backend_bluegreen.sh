#!/bin/bash
# deploy_backend_bluegreen.sh — deploy do backend SEM downtime (requisito 24x7 do Jordan).
#
# Fluxo: build → sobe GREEN (8081, imagem nova) → espera saudável → nginx vira p/ 8081
# → recria o backend primário (8080, imagem nova) → espera saudável → nginx volta p/ 8080
# → remove green. O tráfego público NUNCA fica sem um backend saudável atendendo.
#
# Falhas: se o green não ficar saudável, aborta SEM tocar no tráfego. Se o primário
# não voltar, o tráfego PERMANECE no green (não remove) e o script sai com erro.
set -u
cd /opt/conecta-pro

NGINX_SITE=/etc/nginx/sites-available/erp.conectamais.pro
LOCK=/tmp/conecta_deploy.lock
LOG=/opt/conecta-pro/logs/deploy_bluegreen.log
COMPOSE_BG="docker compose -f docker-compose.yml -f docker-compose.bluegreen.yml"
HEALTH_TIMEOUT=${HEALTH_TIMEOUT:-420}  # 7 min p/ boot do app

log() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }

nginx_upstream_to() {  # $1 = porta destino
  sed -i "0,/server 127.0.0.1:80[0-9][0-9];/s//server 127.0.0.1:$1;/" "$NGINX_SITE"
  nginx -t >/dev/null 2>&1 || { log "ERRO: nginx -t falhou — revertendo"; return 1; }
  systemctl reload nginx
  log "nginx → 127.0.0.1:$1 (reload gracioso)"
}

wait_health() {  # $1 = porta, $2 = nome
  local t=0
  until curl -sf -o /dev/null "http://127.0.0.1:$1/health"; do
    sleep 5; t=$((t+5))
    [ "$t" -ge "$HEALTH_TIMEOUT" ] && { log "TIMEOUT: $2 não ficou saudável em ${HEALTH_TIMEOUT}s"; return 1; }
  done
  log "$2 saudável (porta $1, ${t}s)"
}

cleanup_green() { $COMPOSE_BG rm -sf backend-green >/dev/null 2>&1; }

# ── lock de deploy (convivência entre terminais) ──
if ! mkdir "$LOCK" 2>/dev/null; then
  log "ERRO: lock ocupado ($LOCK) — outro deploy em andamento"; exit 1
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

log "═══ BLUE/GREEN INICIADO ═══"

# 1. Build da imagem nova
log "1/6 build..."
docker compose build backend >>"$LOG" 2>&1 || { log "ERRO no build"; exit 1; }

# 2. Sobe GREEN com a imagem nova (tráfego segue no primário)
log "2/6 subindo green (8081)..."
$COMPOSE_BG up -d --no-deps backend-green >>"$LOG" 2>&1 || { log "ERRO ao subir green"; cleanup_green; exit 1; }
wait_health 8081 "green" || { cleanup_green; log "ABORTADO — tráfego intocado no primário"; exit 1; }

# 3. Vira o tráfego pro GREEN
log "3/6 tráfego → green..."
nginx_upstream_to 8081 || { cleanup_green; exit 1; }

# 4. Recria o primário com a imagem nova (green atendendo)
log "4/6 recriando primário (8080)..."
docker compose up -d --no-deps backend >>"$LOG" 2>&1
if ! wait_health 8080 "primário"; then
  log "ERRO: primário não voltou — TRÁFEGO PERMANECE NO GREEN (não removido). Intervenha."
  exit 1
fi

# 5. Volta o tráfego pro primário
log "5/6 tráfego → primário..."
nginx_upstream_to 8080 || exit 1
sleep 3  # drena conexões keep-alive do green

# 6. Remove o green
log "6/6 removendo green..."
cleanup_green
log "═══ BLUE/GREEN CONCLUÍDO — zero downtime ═══"
