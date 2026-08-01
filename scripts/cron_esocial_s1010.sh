#!/bin/bash
# Retry horário da captura dos S-1010 (códigos legais das rubricas).
# Para sozinho quando capturar (o script grava _CAPTURADO.json e vira no-op).
docker cp /opt/conecta-pro/scripts/esocial_captura_s1010.py conecta-pro-backend:/tmp/cap_s1010.py >/dev/null 2>&1
docker exec -e PYTHONPATH=/app -w /app conecta-pro-backend python3 /tmp/cap_s1010.py 2>&1 \
  | grep -viE "deprecation|rate limit|INFO" >> /opt/conecta-pro/logs/esocial_s1010_captura.log
