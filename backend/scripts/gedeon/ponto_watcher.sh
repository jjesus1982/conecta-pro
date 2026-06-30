#!/usr/bin/env bash
# GEDEON — Vigia do ponto assinado (ponte backend→host p/ Playwright).
# Roda via cron a cada 1 min. Se o orquestrador sinalizou um pedido no Redis
# (gedeon:ponto:request = competência, db1), executa o robô de ponto no HOST e
# escreve o status de volta (gedeon:ponto:status). flock evita execuções sobrepostas.
set -uo pipefail
cd /opt/conecta-pro

exec 9>/tmp/gedeon_ponto_watcher.lock
flock -n 9 || exit 0   # já há um run em andamento

# senha do Redis (do .env, sem expor)
REDIS_PW=$(grep -E '^REDIS_PASSWORD=' .env | cut -d= -f2-)
RC() { docker exec conecta-pro-redis redis-cli -a "$REDIS_PW" --no-auth-warning -n 1 "$@" 2>/dev/null; }

# GETDEL = reivindica o pedido de forma atômica (Redis 6.2+)
COMP=$(RC GETDEL gedeon:ponto:request | tr -d '[:space:]')
[ -z "$COMP" ] && exit 0   # nada pedido

RC SET gedeon:ponto:status "{\"competencia\":\"$COMP\",\"state\":\"running\"}" EX 3600 >/dev/null
if bash backend/scripts/gedeon/ponto_assinado_mensal.sh "$COMP" >> /opt/conecta-pro/rotinas/ponto-assinado.log 2>&1; then
    # extrai "arquivados: N" do último log
    ARQ=$(grep -hoE "arquivados: [0-9]+" /tmp/ponto_assinado_*.log 2>/dev/null | tail -1 | grep -oE "[0-9]+" || echo "")
    RC SET gedeon:ponto:status "{\"competencia\":\"$COMP\",\"state\":\"done\",\"arquivados\":\"$ARQ\"}" EX 3600 >/dev/null
else
    RC SET gedeon:ponto:status "{\"competencia\":\"$COMP\",\"state\":\"error\"}" EX 3600 >/dev/null
fi
