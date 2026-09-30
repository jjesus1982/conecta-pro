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
BACKEND=conecta-pro-backend
CONTAINERS=(conecta-pro-mcp conecta-pro-mcp-internal conecta-pro-mcp-ged conecta-pro-mcp-pessoas)

cd "$REPO" || exit 1
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

# Ponte host->container igual à de scripts/oraculos_diarios.sh:34.
docker exec -e PYTHONPATH=/app "$BACKEND" \
  python3 /app/modules/notifications/tasks_vigia_mcp.py --registrar "$PAYLOAD"
