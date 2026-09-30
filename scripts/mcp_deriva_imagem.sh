#!/usr/bin/env bash
# Deriva de imagem do conector MCP: o que está NO AR é o que está no git?
#
# Por que existe: em 30/09/2026 a imagem em produção era de 19/09 e a parede de testes do
# `mcp-server/` estava vermelha desde as 15:05 do próprio dia. Onze dias de deriva, sem
# alerta nenhum. O único mecanismo que detectou foi alguém rodar `docker build` à mão.
#
# Mora no cron do HOST de propósito, igual à varredura dos oráculos: o dado que interessa
# (label da imagem de cada container) só existe onde o docker está, e o backend não tem
# socket. O script só MEDE e registra a batida; quem toca o sino é o vigia no Celery beat
# (`orq.checar_deriva_mcp`). Quem vigia não depende do mesmo mecanismo que vigia.
#
#   ./scripts/mcp_deriva_imagem.sh           mede e registra a batida
#   ./scripts/mcp_deriva_imagem.sh --build   builda a imagem COM o GIT_SHA e mede
set -uo pipefail

REPO=/opt/conecta-pro
LABEL=br.pro.conectamais.mcp.git_sha
PG=conecta-pro-postgres
CONTAINERS=(conecta-pro-mcp conecta-pro-mcp-internal conecta-pro-mcp-ged conecta-pro-mcp-pessoas)

cd "$REPO" || exit 1
# POSTGRES_USER/POSTGRES_DB saem do mesmo .env que o compose lê.
# shellcheck disable=SC1091
[[ -f .env ]] && set -a && . ./.env && set +a
SHA_GIT=$(git log -1 --format=%H -- mcp-server/)

if [[ "${1:-}" == "--build" ]]; then
  echo "[deriva] buildando com GIT_SHA=$SHA_GIT"
  MCP_GIT_SHA="$SHA_GIT" docker compose -f mcp-server/docker-compose.mcp.yml build || exit 1
fi

# `Config.Labels` do container já traz os labels herdados da imagem.
DERIVOU=false
JSON_CONT=""
for c in "${CONTAINERS[@]}"; do
  sha=$(docker inspect "$c" --format "{{index .Config.Labels \"$LABEL\"}}" 2>/dev/null)
  [[ -z "$sha" ]] && sha=ausente
  [[ "$sha" != "$SHA_GIT" ]] && DERIVOU=true
  JSON_CONT+="$([[ -n "$JSON_CONT" ]] && echo ,)\"$c\":\"$sha\""
done

EM=$(date -u +%Y-%m-%dT%H:%M:%S+00:00)
PAYLOAD="{\"em\":\"$EM\",\"sha_git\":\"$SHA_GIT\",\"derivou\":$DERIVOU,\"containers\":{$JSON_CONT}}"
echo "[deriva] $PAYLOAD"

# Grava a batida direto no postgres, e NÃO por `docker exec` no backend como faz
# scripts/oraculos_diarios.sh:34. A diferença: aquele chama um arquivo que está DENTRO da
# imagem do backend; este script é novo, e o backend é baked — o arquivo só existiria lá
# depois de um rebuild do ERP inteiro. Medido na primeira execução: "can't open file
# /app/modules/notifications/tasks_vigia_mcp.py". Escrever por psql desacopla a medição do
# ciclo de deploy do backend, que é justamente o ciclo que ela existe para vigiar.
docker exec -i "$PG" psql -qtAX -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-conecta_pro}" \
  -v ON_ERROR_STOP=1 -v payload="$PAYLOAD" <<'SQL'
INSERT INTO system_configs (id, chave, valor, descricao, grupo)
VALUES (gen_random_uuid(), 'mcp.deriva_imagem', :'payload',
        'Deriva entre a imagem do conector MCP no ar e mcp-server/ no git (vigiado por orq.checar_deriva_mcp)',
        'mcp')
ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor, updated_at = NOW();
SQL
