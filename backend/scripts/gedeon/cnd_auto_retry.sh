#!/usr/bin/env bash
# GEDEON — Auto-retry das CNDs que faltam. Roda via cron a cada algumas horas.
#
# ⭐ Nasceu só para a Federal (RFB instável "023") e virou geral em 19/08/2026: a MUNICIPAL
# da Patrimonial ficou travada numa restrição da SEMEF que dependia de uma guia ser paga, e
# ninguém tentava de novo — a certidão só sairia se um humano lembrasse de pedir. Prazo que
# depende de alguém lembrar é prazo perdido.
#
# ⭐ Certidão negativa é exigida SÓ da PATRIMONIAL (decisão do Jordan, 19/08): ela é quem
# presta mão de obra e é dela que o contratante cobra CND. A Eletrônica vende segurança
# eletrônica — nota e boleto bastam.
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
FALTANDO=$(docker exec -w /app -e PYTHONPATH=/app conecta-pro-backend python -c "
import os, datetime, re
from sqlalchemy import text
from core.database.session import get_sync_db

# Portais que o robô sabe emitir -> document_type correspondente.
PORTAL = {'federal': 'certidao_negativa_federal',
          'prefeitura': 'certidao_negativa_municipal',
          'sefaz_am': 'certidao_negativa_estadual',
          'cndt': 'certidao_negativa_trabalhista'}
ALVO = '66014833000110'   # só a Patrimonial

falta = []
with get_sync_db() as db:
    for portal, dt in PORTAL.items():
        r = db.execute(text(
            \"SELECT expiry_date FROM ged_certidoes \"
            \" WHERE document_type=:dt \"
            \"   AND replace(replace(replace(coalesce(cnpj,''),'.',''),'/',''),'-','')=:c \"
            \"   AND coalesce(notes,'') NOT LIKE '%\\\"regular\\\": null%' \"
            \"   AND coalesce(notes,'') NOT LIKE '%indeterminado%' LIMIT 1\"),
            {'dt': dt, 'c': ALVO}).fetchone()
        ok = bool(r and r[0] and r[0] > datetime.date.today()+datetime.timedelta(days=15))
        if not ok:
            falta.append(portal)
print(' '.join(falta))
" 2>/dev/null | tail -1)

[ -z "$FALTANDO" ] && exit 0

# Um portal por ciclo: o watcher processa um pedido por vez, e o cron volta em algumas horas.
PORTAL=$(echo "$FALTANDO" | awk '{print $1}')
RC SET gedeon:cnd:request "{\"cnpj\":\"66014833000110\",\"portais\":[\"$PORTAL\"]}" EX 1800 >/dev/null
echo "[$(date '+%F %T')] auto-retry: $PORTAL enfileirado p/ a Patrimonial (faltando: $FALTANDO)"
