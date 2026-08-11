#!/bin/bash
# Varredura diária dos 59 oráculos (exibido == banco). Cron do host, 05:00 America/Manaus.
#
# Roda no container do BACKEND de propósito: um oráculo tem pico de 894 MB (importa o app
# inteiro) e todo worker Celery tem limite de 2 GB com 1,39 GB já em uso — a varredura
# derrubaria por OOM o worker de gov/financeiro/integrações, de madrugada. O backend tem
# 6 GB e é onde os 59 sempre foram rodados à mão.
#
# Verde = silêncio: sai 0 e não escreve no sino. Vermelho: o próprio script Python publica
# o alerta (dedup por dia, mesma mecânica de task_falha) e sai 1.
set -uo pipefail

LOG=/var/log/conecta-oraculos.log
CONTAINER=conecta-pro-backend

{
  echo "═══ $(date '+%Y-%m-%d %H:%M:%S') varredura dos oráculos ═══"

  if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    echo "ERRO: $CONTAINER não está de pé — varredura não rodou (isto não é 'tudo verde')"
    exit 2
  fi

  # Deploy em curso recria o backend no meio e mata tudo dali em diante: já produziu duas
  # varreduras com 38 e 17 "falhas" que não existiam. Melhor não rodar do que mentir.
  if [ -d /tmp/conecta_deploy.lock ]; then
    echo "deploy em curso — varredura adiada (rodar à mão depois)"
    exit 0
  fi

  docker exec -e PYTHONPATH=/app "$CONTAINER" \
    python3 /app/modules/notifications/tasks_oraculos.py --varrer
  echo "saída: $?"
} >> "$LOG" 2>&1
