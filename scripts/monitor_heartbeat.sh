#!/bin/bash
# ═══════════════════════════════════════════════
# Heartbeat do Monitor Conecta PRO
# Roda a cada 6h via cron
# Se Jordan parar de receber → algo está errado
# ═══════════════════════════════════════════════

BOT_TOKEN="${MONITOR_BOT_TOKEN:-}"  # pragma: allowlist secret
CHAT_ID="${MONITOR_CHAT_ID:-5536961034}"
STATE_FILE="/opt/conecta-pro/reports/monitor_state.json"
REGRESSION_FILE="/opt/conecta-pro/reports/regressoes.json"
LOG_FILE="/opt/conecta-pro/logs/monitor.log"
HEARTBEAT_LOG="/opt/conecta-pro/logs/heartbeat.log"
HORA=$(date '+%d/%m/%Y %H:%M')

# ── Coletar métricas do sistema ─────────────────
CPU=$(top -bn1 | grep "Cpu(s)" | \
  awk '{print $2}' | cut -d'%' -f1 2>/dev/null \
  || echo "?")

MEM=$(free -m 2>/dev/null | \
  awk '/^Mem:/{printf "%.0f%%", $3/$2*100}' \
  || echo "?")

DISCO=$(df -h / 2>/dev/null | \
  awk 'NR==2{print $5}' || echo "?")

UPTIME=$(uptime -p 2>/dev/null \
  | sed 's/up //' || echo "N/A")

# ── Coletar dados do estado persistente ─────────
CICLOS=$(python3 -c "
import json
try:
    s = json.load(open('$STATE_FILE'))
    print(s.get('ciclos_executados', 0))
except:
    print('?')
" 2>/dev/null)

SCORE=$(python3 -c "
import json
try:
    s = json.load(open('$STATE_FILE'))
    h = s.get('score_historico', [])
    if h:
        scores = [x['score'] for x in h[-3:]]
        print(round(sum(scores)/len(scores), 1))
    else:
        print('?')
except:
    print('?')
" 2>/dev/null)

TENDENCIA=$(python3 -c "
import sys
sys.path.insert(0, '/opt/conecta-pro/agents')
try:
    from monitor_state import get_tendencia
    print(get_tendencia())
except:
    print('→')
" 2>/dev/null)

CORRECOES=$(python3 -c "
import json
try:
    s = json.load(open('$STATE_FILE'))
    print(s.get('correcoes_aplicadas_total', 0))
except:
    print(0)
" 2>/dev/null)

BUGS_PERSIST=$(python3 -c "
import json
try:
    s = json.load(open('$STATE_FILE'))
    p = [b for b in s.get('bugs_persistentes', [])
         if b.get('ocorrencias', 0) >= 3]
    print(len(p))
except:
    print(0)
" 2>/dev/null)

REGRESSOES=$(python3 -c "
import json
try:
    h = json.load(open('$REGRESSION_FILE'))
    print(len(h))
except:
    print(0)
" 2>/dev/null)

MELHOR_SCORE=$(python3 -c "
import json
try:
    s = json.load(open('$STATE_FILE'))
    print(s.get('melhor_score', '?'))
except:
    print('?')
" 2>/dev/null)

PRIMEIRA_EXEC=$(python3 -c "
import json
try:
    s = json.load(open('$STATE_FILE'))
    print(s.get('primeira_execucao', '?')[:10])
except:
    print('?')
" 2>/dev/null)

LOG_SIZE=$(du -sh $LOG_FILE 2>/dev/null \
  | cut -f1 || echo "N/A")

# ── Verificar saúde dos serviços ────────────────
BACKEND=$(curl -sf -o /dev/null -w "%{http_code}" \
  http://127.0.0.1:8080/docs 2>/dev/null)
BACKEND_STATUS="✅ Online"
[ "$BACKEND" != "200" ] && \
  BACKEND_STATUS="❌ Offline ($BACKEND)"

PM2_STATUS=$(pm2 list 2>/dev/null | \
  grep -c "online" || echo "0")
PM2_INFO="✅ $PM2_STATUS processo(s) online"
[ "$PM2_STATUS" = "0" ] && \
  PM2_INFO="❌ Nenhum processo PM2 online"

REDIS=$(docker exec \
  $(docker ps --filter ancestor=redis \
    --format '{{.Names}}' | head -1) \
  redis-cli ping 2>/dev/null || echo "FAIL")
REDIS_STATUS="✅ OK"
[ "$REDIS" != "PONG" ] && \
  REDIS_STATUS="❌ Falhou"

# ── Score colorido ───────────────────────────────
SCORE_EMOJI="📊"
if [ "$SCORE" != "?" ]; then
    SCORE_NUM=$(echo $SCORE | \
      python3 -c "import sys; \
      v=float(sys.stdin.read().strip()); \
      print('high' if v>=8 else \
      'med' if v>=6 else 'low')" 2>/dev/null)
    [ "$SCORE_NUM" = "high" ] && SCORE_EMOJI="🟢"
    [ "$SCORE_NUM" = "med" ] && SCORE_EMOJI="🟡"
    [ "$SCORE_NUM" = "low" ] && SCORE_EMOJI="🔴"
fi

# ── Montar mensagem ──────────────────────────────
MSG="💚 <b>HEARTBEAT — MONITOR ATIVO</b>
━━━━━━━━━━━━━━━━━━━
⏰ <b>$HORA</b>

$SCORE_EMOJI <b>Score:</b> $SCORE/10
📈 <b>Tendência:</b> $TENDENCIA
🏆 <b>Melhor score:</b> $MELHOR_SCORE/10

🖥️ <b>Infraestrutura:</b>
  • Backend: $BACKEND_STATUS
  • Frontend: $PM2_INFO
  • Redis: $REDIS_STATUS
  • CPU: $CPU% | RAM: $MEM | Disco: $DISCO

📊 <b>Estatísticas:</b>
  • Ciclos executados: $CICLOS
  • Correções aplicadas: $CORRECOES
  • Bugs persistentes: $BUGS_PERSIST
  • Regressões registradas: $REGRESSOES

⚙️ <b>Sistema:</b>
  • Uptime: $UPTIME
  • Log: $LOG_SIZE
  • Ativo desde: $PRIMEIRA_EXEC

✅ Próximo heartbeat em ~6h"

# ── Enviar para Telegram ─────────────────────────
curl -sf -X POST \
  "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
  -H "Content-Type: application/json" \
  -d "{
    \"chat_id\": \"${CHAT_ID}\",
    \"text\": \"${MSG}\",
    \"parse_mode\": \"HTML\"
  }" > /dev/null 2>&1

RESULT=$?
if [ $RESULT -eq 0 ]; then
    echo "[$HORA] Heartbeat enviado OK" \
      >> $HEARTBEAT_LOG
else
    echo "[$HORA] Heartbeat FALHOU" \
      >> $HEARTBEAT_LOG
fi
