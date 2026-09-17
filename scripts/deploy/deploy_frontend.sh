#!/usr/bin/env bash
# deploy_frontend.sh — Deploy Next.js frontend sem ChunkLoadError
#
# POR QUÊ PRESERVAR CHUNKS ANTIGOS:
#   Next.js gera chunks com hash de conteúdo (ex: ee79b3aa27b940fc.js).
#   Browsers cacheiam com `Cache-Control: immutable, 1y`.
#   Se o nginx recarregar antes do browser, o browser pede o chunk antigo → 404 → ChunkLoadError.
#   Solução: manter os chunks antigos acessíveis no container durante a transição.
#
# COMO O NGINX FUNCIONA AQUI:
#   /_next/static/ → proxy_pass http://frontend (container 127.0.0.1:3001)
#   proxy_cache static_cache + proxy_cache_valid 200 365d
#   Os chunks ficam no container — não no host filesystem.
#   Por isso: preservar chunks antigos = copiá-los de volta ao container após o deploy.
#
# USO:
#   ./scripts/deploy/deploy_frontend.sh [--dry-run]

set -euo pipefail

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

FRONTEND_DIR="/opt/conecta-pro/frontend"
CONTAINER_NAME="conecta-pro-frontend"
BACKUP_DIR="/opt/conecta-pro/.chunk_archive"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

log()  { echo "[$(date +%H:%M:%S)] $*"; }
die()  { echo "[ERROR] $*" >&2; exit 1; }
run()  { $DRY_RUN && echo "[DRY-RUN] $*" || eval "$@"; }

# ── STEP 0: Resolve container name (pode ter prefixo de hash)
CONTAINER=$(docker ps --format "{{.Names}}" | grep "$CONTAINER_NAME" | head -1)
[[ -z "$CONTAINER" ]] && die "Container $CONTAINER_NAME não encontrado. Verifique: docker ps"
log "Container: $CONTAINER"

# ── STEP 1: Estado de partida (a decisão de abortar é no STEP 4.1, depois do build)
#
# Origem: 17/09/2026. Esta guarda ficava AQUI, antes do build, e comparava o build VELHO do
# host com o que já estava no container. Com fonte nova ainda não buildada os dois batem, e
# o script saía com "nada a fazer" e exit 0 — verde, sem publicar nada. Perdi um deploy
# inteiro do fix do link de assinatura assim. A pergunta certa ("o build novo é igual ao
# que está lá?") só pode ser feita DEPOIS de buildar.
HOST_BUILD_ID=$(cat "$FRONTEND_DIR/.next/BUILD_ID" 2>/dev/null || echo "NONE")
CONTAINER_BUILD_ID=$(docker exec "$CONTAINER" cat /app/.next/BUILD_ID 2>/dev/null || echo "NONE")
log "BUILD_ID (antes do build) host=$HOST_BUILD_ID  container=$CONTAINER_BUILD_ID"

# ── STEP 2: Verificar symlinks no build (§15.3 — usar standalone/ se symlinks detectados)
SYMLINKS_STATIC=$(find "$FRONTEND_DIR/.next/static" -type l 2>/dev/null | wc -l)
SYMLINKS_SERVER=$(find "$FRONTEND_DIR/.next/server" -type l 2>/dev/null | wc -l)
log "Symlinks: static/$SYMLINKS_STATIC  server/$SYMLINKS_SERVER"

if [[ "$SYMLINKS_STATIC" -gt 0 || "$SYMLINKS_SERVER" -gt 0 ]]; then
    log "⚠️  Symlinks detectados — usando standalone/ em vez de .next/ direto"
    STATIC_SRC="$FRONTEND_DIR/.next/standalone/.next/static"
    SERVER_SRC="$FRONTEND_DIR/.next/standalone/.next/server"
else
    STATIC_SRC="$FRONTEND_DIR/.next/static"
    SERVER_SRC="$FRONTEND_DIR/.next/server"
fi

# ── STEP 3: Salvar chunks antigos do container para arquivo local (INV-2: nunca deletar)
ARCHIVE_PATH="$BACKUP_DIR/$TIMESTAMP"
log "Arquivando chunks antigos do container → $ARCHIVE_PATH"
run "mkdir -p $ARCHIVE_PATH"
run "docker cp $CONTAINER:/app/.next/static/chunks/. $ARCHIVE_PATH/"
ARCHIVED=$(ls "$ARCHIVE_PATH" 2>/dev/null | wc -l || echo "?")
log "Chunks arquivados: $ARCHIVED"

# ── STEP 4: Build Next.js no host (serializado — nunca simultâneo)
log "Iniciando build Next.js..."
run "cd $FRONTEND_DIR && NODE_OPTIONS=--max-old-space-size=4096 npm run build"
NEW_BUILD_ID=$(cat "$FRONTEND_DIR/.next/BUILD_ID" 2>/dev/null || echo "NONE")
log "Novo BUILD_ID: $NEW_BUILD_ID"

# ── STEP 4.1: AGORA sim dá para dizer se há o que publicar
if [[ "$NEW_BUILD_ID" == "$CONTAINER_BUILD_ID" && "$NEW_BUILD_ID" != "NONE" ]]; then
    log "BUILD_ID do build novo é o mesmo do container — nada mudou. Encerrando."
    exit 0
fi

# ── STEP 5: Sincronizar novo build → container
log "Sincronizando novo build → $CONTAINER"
run "docker cp $STATIC_SRC/.  $CONTAINER:/app/.next/static/"
run "docker cp $SERVER_SRC/.  $CONTAINER:/app/.next/server/"
run "docker cp $FRONTEND_DIR/.next/standalone/. $CONTAINER:/app/.next/standalone/" 2>/dev/null || true
run "docker cp $FRONTEND_DIR/.next/BUILD_ID     $CONTAINER:/app/.next/BUILD_ID"
run "docker cp $FRONTEND_DIR/.next/routes-manifest.json $CONTAINER:/app/.next/" 2>/dev/null || true
# Manifestos raiz (app-path-routes-manifest, prerender-manifest, build-manifest, etc.)
# Sem estes arquivos rotas novas ficam ausentes e retornam 404 mesmo com page.js correto
for _manifest in app-path-routes-manifest.json app-paths-manifest.json build-manifest.json \
                 fallback-build-manifest.json prerender-manifest.json \
                 react-loadable-manifest.json export-marker.json; do
    [[ -f "$FRONTEND_DIR/.next/$_manifest" ]] && \
        run "docker cp $FRONTEND_DIR/.next/$_manifest $CONTAINER:/app/.next/$_manifest" || true
done

# ── STEP 6: Reinjetar chunks antigos no container (preservação anti-ChunkLoadError)
log "Reinjetando chunks antigos → container (preservação)"
if [[ -d "$ARCHIVE_PATH" && "$(ls -A "$ARCHIVE_PATH")" ]]; then
    run "docker cp $ARCHIVE_PATH/. $CONTAINER:/app/.next/static/chunks/"
    log "Chunks antigos preservados no container ✅"
else
    log "Nenhum chunk antigo para reinjetar (primeiro deploy?)"
fi

# ── STEP 7: Reiniciar container + pm2
log "Reiniciando container..."
run "docker restart $CONTAINER"
log "Aguardando container ficar healthy..."
if ! $DRY_RUN; then
    sleep 15
    for i in $(seq 1 30); do
        STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || echo "none")
        [[ "$STATUS" == "healthy" || "$STATUS" == "none" ]] && break
        [[ $i -eq 30 ]] && die "Container não ficou healthy após 45s"
        sleep 1
    done
fi
run "pm2 restart all" || true

# ── STEP 8: Validação
log "Validando..."
if ! $DRY_RUN; then sleep 3; fi
HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" http://127.0.0.1:3001/ 2>/dev/null || echo "000")
CONTAINER_BUILD_ID_NEW=$(docker exec "$CONTAINER" cat /app/.next/BUILD_ID 2>/dev/null || echo "ERR")
CONTAINER_CHUNKS=$(docker exec "$CONTAINER" find /app/.next/static/chunks -name "*.js" | wc -l 2>/dev/null || echo "?")

log "HTTP /: $HTTP_CODE"
log "BUILD_ID container: $CONTAINER_BUILD_ID_NEW (host: $NEW_BUILD_ID)"
log "Chunks no container: $CONTAINER_CHUNKS"

[[ "$HTTP_CODE" == "200" ]] || die "Frontend não respondeu HTTP 200 (got $HTTP_CODE)"
[[ "$CONTAINER_BUILD_ID_NEW" == "$NEW_BUILD_ID" ]] || die "BUILD_ID mismatch host≠container"

log ""
log "✅  Deploy concluído com sucesso"
log "    BUILD_ID: $NEW_BUILD_ID"
log "    Chunks container: $CONTAINER_CHUNKS"
log "    Arquivo de chunks antigos: $ARCHIVE_PATH"
