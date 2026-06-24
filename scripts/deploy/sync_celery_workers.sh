#!/bin/bash
# Sync módulo para todos os workers Celery
# Uso: ./sync_celery_workers.sh nome_do_modulo
MODULO=${1:?'Informe o módulo: ./sync_celery_workers.sh gedeon'}
for CONTAINER in conecta-pro-backend conecta-pro-celery-beat conecta-pro-celery-batch \
  conecta-pro-celery-operacional conecta-pro-celery-integrations conecta-pro-celery-priority \
  conecta-pro-celery-nfse conecta-pro-celery-sefaz; do
  # Limpa pyc recursivo (não só o __pycache__ raiz) — evita bytecode stale em submódulos
  docker exec $CONTAINER find /app/modules/$MODULO -name "*.pyc" -delete 2>/dev/null || true
  # Remove aninhamento acidental de execuções antigas (bug do docker cp sem /.)
  docker exec $CONTAINER rm -rf "/app/modules/$MODULO/$MODULO" 2>/dev/null || true
  # Copia o CONTEÚDO do módulo (sufixo /.) PARA DENTRO do destino — nunca aninha
  docker cp "backend/modules/$MODULO/." "$CONTAINER:/app/modules/$MODULO/" && echo "OK: $CONTAINER"
done
docker exec conecta-pro-backend kill -HUP 1

# Sync celery_app.py para todos os workers
echo "=== Sincronizando celery_app.py ==="
for C in conecta-pro-celery-beat conecta-pro-celery-batch \
  conecta-pro-celery-operacional conecta-pro-celery-integrations \
  conecta-pro-celery-priority conecta-pro-celery-nfse conecta-pro-celery-sefaz; do
  docker exec $C find /app/__pycache__ -name "celery_app*.pyc" -delete 2>/dev/null || true
  docker cp backend/celery_app.py $C:/app/celery_app.py && echo "OK: $C"
  docker exec $C python3 -c "import os,signal; os.kill(1,signal.SIGHUP)" 2>/dev/null || true
done
