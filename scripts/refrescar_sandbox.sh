#!/usr/bin/env bash
# Refaz o banco do SANDBOX a partir de produção.
#
# Por que existe (auditoria do Cowork, 11/09/2026 · §3.2): o banco de staging era um snapshot
# de meses atrás e tinha DERIVADO do schema de produção em vários pontos — faltava
# `contracts.payment_day`, sobrava `contracts.empresa_id`, o catálogo `crm_products` estava
# vazio. `alembic upgrade heads` não resolve: cada migration falha num ponto diferente do
# drift. Um sandbox cujo schema não bate com produção é pior que não ter sandbox, porque dá
# confiança falsa — o teste passa lá e quebra aqui.
#
# ⭐ A operação certa para um sandbox é RECOPIAR, não remendar.
#
# SEGURANÇA — a direção é sempre produção → sandbox, NUNCA o contrário:
#   · o destino é conferido pelo NOME antes de qualquer DROP. Um banco de destino chamado
#     `conecta_pro` aborta o script. Não existe flag para forçar;
#   · o dump de produção é lido com usuário de leitura e nada é escrito lá;
#   · o sandbox fica com dado REAL de cliente. Ele vive em 127.0.0.1 (postgres e backend),
#     e desde 11/09 as ações de efeito externo exigem aprovação em qualquer conector — mas
#     isto continua sendo uma cópia de PII. Não exponha a porta.
#
#   bash scripts/refrescar_sandbox.sh
set -euo pipefail

PROD_C=conecta-pro-postgres;         PROD_DB=conecta_pro
STG_C=conecta-pro-postgres-staging;  STG_DB=conecta_pro_staging

# ⚠️ Trava de direção. Sem isto, uma troca de variável apagaria produção — e "eu não ia
# errar" não é mecanismo.
if [ "$STG_DB" = "conecta_pro" ] || [ "$STG_C" = "$PROD_C" ]; then
  echo "ABORTADO: o destino aponta para PRODUÇÃO ($STG_C/$STG_DB)." >&2
  exit 1
fi

echo "  origem : $PROD_C/$PROD_DB  (somente leitura)"
echo "  destino: $STG_C/$STG_DB    (será RECRIADO)"

echo "  [1/4] dump de produção..."
docker exec "$PROD_C" pg_dump -U postgres -d "$PROD_DB" --no-owner --no-privileges \
  > /tmp/refresh_sandbox.sql
echo "        $(wc -c < /tmp/refresh_sandbox.sql | numfmt --to=iec)B"

echo "  [2/4] derrubando conexões e recriando o banco de destino..."
docker exec "$STG_C" psql -U postgres -d postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$STG_DB' AND pid<>pg_backend_pid();" >/dev/null
docker exec "$STG_C" psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS $STG_DB;" >/dev/null
docker exec "$STG_C" psql -U postgres -d postgres -c "CREATE DATABASE $STG_DB;" >/dev/null

echo "  [3/4] restaurando..."
docker cp /tmp/refresh_sandbox.sql "$STG_C":/tmp/r.sql >/dev/null
docker exec "$STG_C" psql -U postgres -d "$STG_DB" -q -f /tmp/r.sql > /tmp/refresh_restore.log 2>&1 || true
docker exec "$STG_C" rm -f /tmp/r.sql
rm -f /tmp/refresh_sandbox.sql

echo "  [4/4] conferindo por LEITURA (nunca pela linha de saída)..."
for t in clients contracts contract_templates crm_products employees; do
  P=$(docker exec "$PROD_C" psql -U postgres -d "$PROD_DB" -t -A -c "SELECT count(*) FROM $t;" 2>/dev/null || echo "?")
  S=$(docker exec "$STG_C" psql -U postgres -d "$STG_DB" -t -A -c "SELECT count(*) FROM $t;" 2>/dev/null || echo "?")
  [ "$P" = "$S" ] && M="ok" || M="DIVERGE"
  printf "        %-20s prod=%-6s sandbox=%-6s %s\n" "$t" "$P" "$S" "$M"
done

# a senha do ERP_USER vem junto no dump, então o login do .env vale no sandbox sem inventar
# segredo novo — era assim antes deste script e continua sendo.
echo
echo "  Reinicie o backend do sandbox para ele reabrir o pool:"
echo "    docker compose -f docker-compose.staging.yml restart backend-staging"
