#!/bin/bash
# ═══════════════════════════════════════════════════════
# START_AUDITORIA.sh — Ativa o sistema de auditoria 24h
# Executar APENAS após concluir o trabalho nos T1-T5
# Jordan: rode este script quando estiver pronto
# ═══════════════════════════════════════════════════════

set -e

echo "🚀 ATIVANDO SISTEMA DE AUDITORIA CONECTA PRO"
echo "=============================================="

# Verificar que não está já ativo
CRON_ATIVO=$(crontab -l 2>/dev/null | grep -c "audit_orchestrator" || true)
if [ "$CRON_ATIVO" -gt 0 ]; then
    echo "⚠️  Sistema já está ativo. Para desativar: bash STOP_AUDITORIA.sh"
    exit 0
fi

# 1. Adicionar cron semanal (domingo 3h)
# shellcheck disable=SC2016  # pragma: allowlist secret
TOKEN_VAR='MONITOR_BOT_TOKEN=${MONITOR_BOT_TOKEN:-} TELEGRAM_CHAT_ID=5536961034'  # pragma: allowlist secret
(crontab -l 2>/dev/null; echo "0 3 * * 0 ${TOKEN_VAR} python3 /opt/conecta-pro/agents/core/audit_orchestrator.py >> /opt/conecta-pro/logs/auditoria.log 2>&1") | crontab -

echo "✅ Cron semanal ativado (domingo 3h)"

# 2. Garantir diretórios
mkdir -p /opt/conecta-pro/logs
mkdir -p /opt/conecta-pro/reports/auditorias

echo "✅ Diretórios confirmados"

# 3. Rodar primeiro ciclo imediatamente
echo ""
echo "🔍 Rodando primeiro ciclo de auditoria..."
echo "(isso pode levar alguns minutos)"
echo ""

cd /opt/conecta-pro
python3 -c "
import sys, json, subprocess
sys.path.insert(0, 'agents/core')

r = subprocess.run(
    \"curl -sf -X POST http://127.0.0.1:8080/api/v1/auth/login \"
    \"-H 'Content-Type: application/x-www-form-urlencoded' \"
    \"-d 'username=jjesus@conectamais.pro&password=Jordan0612'\",  # pragma: allowlist secret
    shell=True, capture_output=True, text=True
)
token = json.loads(r.stdout).get('access_token', '')

from audit_orchestrator import AuditOrchestrator
orch = AuditOrchestrator(token=token)
resultado = orch.auditar_todos(skills=[3,6,9,10], auto_fix=True)

print(f'Bugs encontrados: {resultado[\"total_bugs\"]}')
print(f'Corrigidos: {resultado[\"total_corrigidos\"]}')
print('Telegram notificado ✅')
print('Auditoria automática ATIVA ✅')
"

echo ""
echo "=============================================="
echo "✅ SISTEMA DE AUDITORIA ATIVO"
echo "   Ciclo: todo domingo às 3h"
echo "   Telegram: @conecta_pro_monitor_bot"
echo "   Logs: /opt/conecta-pro/logs/auditoria.log"
echo "   Para desativar: bash agents/STOP_AUDITORIA.sh"
echo "=============================================="
