#!/bin/sh
# Entrypoint script para AlertManager
# [FASE2-JL 20260612] OpenClaw foi REMOVIDO do sistema — o webhook antigo era um
# endpoint MORTO (alertas reais nunca chegavam a ninguem). Agora: Telegram NATIVO
# do Alertmanager (bot das notificacoes reais), só alertas por limiar do Prometheus.
# Requer env: TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID.

CONFIG_FILE=/etc/alertmanager/alertmanager.yml

cat > "$CONFIG_FILE" << EOF
# AlertManager Configuration - ERP Conecta Mais
# Telegram nativo — alertas REAIS por limiar (sem IA, sem alucinacao)
global:
  resolve_timeout: 5m

templates:
  - '/etc/alertmanager/templates/*.tmpl'

route:
  receiver: 'telegram-default'
  group_by: ['alertname', 'severity', 'job']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - match:
        severity: critical
      receiver: 'telegram-critical'
      repeat_interval: 1h
    - match:
        severity: warning
      receiver: 'telegram-default'
      group_wait: 1m
      repeat_interval: 8h
    - match:
        severity: info
      receiver: 'telegram-default'
      group_wait: 5m
      repeat_interval: 24h

receivers:
  - name: 'telegram-default'
    telegram_configs:
      - bot_token: '${TELEGRAM_BOT_TOKEN}'
        chat_id: ${TELEGRAM_CHAT_ID}
        send_resolved: true
        parse_mode: 'HTML'
        message: '{{ if eq .Status "firing" }}⚠️{{ else }}✅{{ end }} <b>{{ .GroupLabels.alertname }}</b> ({{ .Status }}){{ range .Alerts }}
{{ .Annotations.summary }}{{ if .Annotations.description }} — {{ .Annotations.description }}{{ end }}{{ end }}'
  - name: 'telegram-critical'
    telegram_configs:
      - bot_token: '${TELEGRAM_BOT_TOKEN}'
        chat_id: ${TELEGRAM_CHAT_ID}
        send_resolved: true
        parse_mode: 'HTML'
        message: '🚨 <b>CRÍTICO: {{ .GroupLabels.alertname }}</b> ({{ .Status }}){{ range .Alerts }}
{{ .Annotations.summary }}{{ if .Annotations.description }} — {{ .Annotations.description }}{{ end }}{{ end }}'

inhibit_rules:
  - source_match:
      severity: 'critical'
    target_match:
      severity: 'warning'
    equal: ['alertname', 'job']
EOF

exec /bin/alertmanager \
  --config.file="$CONFIG_FILE" \
  --storage.path=/alertmanager \
  --web.external-url="${WEB_EXTERNAL_URL:-http://localhost:9093}" \
  --web.route-prefix=/ \
  "$@"
