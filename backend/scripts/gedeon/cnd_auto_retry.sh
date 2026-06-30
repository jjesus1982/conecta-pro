#!/usr/bin/env bash
# GEDEON — Auto-retry da CND Federal (RFB instável "023"). Roda via cron a cada algumas horas.
# Só dispara a emissão se NÃO houver CND Federal válida (PDF presente + validade > hoje+15d).
# Quando a RFB cooperar, o cnd_watcher emite, registra e leva ao kit; aí o retry para sozinho.
set -uo pipefail
cd /opt/conecta-pro

exec 9>/tmp/gedeon_cnd_retry.lock
flock -n 9 || exit 0

REDIS_PW=$(grep -E '^REDIS_PASSWORD=' .env | cut -d= -f2-)
RC() { docker exec conecta-pro-redis redis-cli -a "$REDIS_PW" --no-auth-warning -n 1 "$@" 2>/dev/null; }

# já existe um pedido em andamento? não atropela
[ "$(RC EXISTS gedeon:cnd:request)" = "1" ] && exit 0

# precisa emitir a Federal? (sem PDF válido)
NEED=$(docker exec -w /app -e PYTHONPATH=/app conecta-pro-backend python -c "
import os, datetime
from sqlalchemy import text
from core.database.session import get_sync_db
need=1
with get_sync_db() as db:
    r=db.execute(text(\"SELECT file_path, expiry_date FROM ged_certidoes WHERE document_type='certidao_negativa_federal' LIMIT 1\")).fetchone()
    if r and r[0] and os.path.exists(r[0]) and r[1] and r[1] > datetime.date.today()+datetime.timedelta(days=15):
        need=0
print(need)
" 2>/dev/null | tail -1)

[ "$NEED" = "0" ] && exit 0

# pede a emissão da Federal (o cnd_watcher de 1 min processa)
CNPJ=$(grep -E '^NFSE_MANAUS_CNPJ=' .env | cut -d= -f2- || echo "35710481000103")
[ -z "$CNPJ" ] && CNPJ="35710481000103"
RC SET gedeon:cnd:request "{\"cnpj\":\"$CNPJ\",\"portais\":[\"federal\"]}" EX 1800 >/dev/null
echo "[$(date '+%F %T')] auto-retry: pedido de emissão da CND Federal enfileirado"
