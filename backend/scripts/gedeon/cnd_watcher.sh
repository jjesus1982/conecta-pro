#!/usr/bin/env bash
# GEDEON — Vigia de emissão de CND (ponte backend→host p/ Playwright + 2captcha).
# Cron 1 min: se o backend pediu (gedeon:cnd:request no Redis db1), emite as CNDs no HOST
# (robô cnd_robot), salva os PDFs, registra em ged_certidoes (via container) e escreve o status.
set -uo pipefail
cd /opt/conecta-pro

exec 9>/tmp/gedeon_cnd_watcher.lock
flock -n 9 || exit 0   # já rodando

REDIS_PW=$(grep -E '^REDIS_PASSWORD=' .env | cut -d= -f2-)
RC() { docker exec conecta-pro-redis redis-cli -a "$REDIS_PW" --no-auth-warning -n 1 "$@" 2>/dev/null; }

REQ=$(RC GETDEL gedeon:cnd:request)
[ -z "$REQ" ] && exit 0

set -a; source .env; set +a   # TWOCAPTCHA_API_KEY
CNPJ=$(echo "$REQ" | python3 -c "import sys,json;print(json.load(sys.stdin).get('cnpj','35710481000103'))" 2>/dev/null || echo "35710481000103")
PORTAIS=$(echo "$REQ" | python3 -c "import sys,json;print(' '.join(json.load(sys.stdin).get('portais',['sefaz_am','cndt','prefeitura'])))" 2>/dev/null || echo "sefaz_am cndt prefeitura")

LOG="/tmp/cnd_emit_$(date +%Y%m%d_%H%M%S).log"
: > /opt/conecta-pro/uploads/cnd_results.jsonl   # limpa resultados anteriores

for P in $PORTAIS; do
    RC SET gedeon:cnd:status "{\"state\":\"running\",\"atual\":\"$P\",\"cnpj\":\"$CNPJ\"}" EX 1800 >/dev/null
    OUT=$(timeout 400 python3 backend/scripts/gedeon/cnd_robot.py "$P" "$CNPJ" 2>>"$LOG" | grep '^{' | tail -1)
    [ -n "$OUT" ] && echo "$OUT" >> /opt/conecta-pro/uploads/cnd_results.jsonl
done

# registra em ged_certidoes (no container, que enxerga /app/uploads/cnd_results.jsonl + os PDFs)
cp backend/scripts/gedeon/register_cnds.py uploads/_register_cnds.py
docker exec -w /app -e PYTHONPATH=/app conecta-pro-backend python /app/uploads/_register_cnds.py >> "$LOG" 2>&1 || true
rm -f uploads/_register_cnds.py

RC SET gedeon:cnd:status "{\"state\":\"done\",\"cnpj\":\"$CNPJ\",\"ts\":\"$(date -u +%FT%TZ)\"}" EX 1800 >/dev/null
echo "[$(date '+%F %T')] CND emissão concluída p/ $CNPJ ($PORTAIS)" >> "$LOG"
