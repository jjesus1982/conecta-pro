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
# ⚠️ MULTI-CNPJ (19/08/2026). Isto perguntava "existe ALGUMA federal válida?" — sem CNPJ,
# com LIMIT 1 — e pedia a emissão sempre pelo CNPJ da Eletrônica. Com a Eletrônica em dia, o
# retry concluía "não precisa" e a PATRIMONIAL nunca seria emitida: um CNPJ inteiro ficava
# fora da automação sem nada acusar. Agora pergunta POR EMPRESA e emite para quem falta.
CNPJ_FALTANDO=$(docker exec -w /app -e PYTHONPATH=/app conecta-pro-backend python -c "
import os, datetime, re
from sqlalchemy import text
from core.database.session import get_sync_db
so = lambda c: re.sub(r'\\D', '', c or '')
falta = []
with get_sync_db() as db:
    for (cnpj,) in db.execute(text(\"SELECT cnpj FROM empresas WHERE lower(coalesce(status,'ativa')) NOT IN ('inativa','encerrada') ORDER BY slug\")).fetchall():
        c = so(cnpj)
        if not c:
            continue
        r = db.execute(text(
            \"SELECT file_path, expiry_date FROM ged_certidoes \"
            \" WHERE document_type='certidao_negativa_federal' \"
            \"   AND replace(replace(replace(coalesce(cnpj,''),'.',''),'/',''),'-','') = :c LIMIT 1\"),
            {'c': c}).fetchone()
        valida = bool(r and r[0] and os.path.exists(r[0]) and r[1]
                      and r[1] > datetime.date.today()+datetime.timedelta(days=15))
        if not valida:
            falta.append(c)
print(' '.join(falta))
" 2>/dev/null | tail -1)

[ -z "$CNPJ_FALTANDO" ] && exit 0

# pede a emissão da Federal do PRIMEIRO que falta (o cnd_watcher de 1 min processa um pedido
# por vez; o próximo ciclo do cron pega o seguinte).
CNPJ=$(echo "$CNPJ_FALTANDO" | awk '{print $1}')
RC SET gedeon:cnd:request "{\"cnpj\":\"$CNPJ\",\"portais\":[\"federal\"]}" EX 1800 >/dev/null
echo "[$(date '+%F %T')] auto-retry: CND Federal enfileirada p/ $CNPJ (faltando: $CNPJ_FALTANDO)"
