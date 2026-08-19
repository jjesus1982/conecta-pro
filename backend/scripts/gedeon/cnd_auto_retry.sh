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
# A consulta vive em cnd_faltantes.py — inline, as aspas eram destroçadas pelo shell e o
# SyntaxError ia para /dev/null: o retry saía "nada falta" e nunca pedia certidão nenhuma.
cp backend/scripts/gedeon/cnd_faltantes.py uploads/_cnd_faltantes.py
FALTANDO=$(docker exec -w /app -e PYTHONPATH=/app conecta-pro-backend \
             python /app/uploads/_cnd_faltantes.py 2>/tmp/cnd_faltantes.err | tr '\n' ' ')
RC_CONSULTA=$?
rm -f uploads/_cnd_faltantes.py

# ⚠️ "não consegui perguntar" NÃO é "nada falta". Sem esta distinção o cron fica mudo para
# sempre no dia em que a consulta quebrar — foi assim que este script passou a mentir.
if [ "$RC_CONSULTA" != "0" ]; then
    echo "[$(date '+%F %T')] auto-retry: FALHA ao consultar certidões — $(head -2 /tmp/cnd_faltantes.err 2>/dev/null)"
    exit 1
fi

[ -z "$FALTANDO" ] && exit 0

# Um portal por ciclo: o watcher processa um pedido por vez, e o cron volta em algumas horas.
PORTAL=$(echo "$FALTANDO" | awk '{print $1}')
RC SET gedeon:cnd:request "{\"cnpj\":\"66014833000110\",\"portais\":[\"$PORTAL\"]}" EX 1800 >/dev/null
echo "[$(date '+%F %T')] auto-retry: $PORTAL enfileirado p/ a Patrimonial (faltando: $FALTANDO)"
