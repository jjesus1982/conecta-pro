#!/usr/bin/env bash
# GEDEON — Vigia de emissão de CND (ponte backend→host p/ Playwright + 2captcha).
# Cron 1 min: se o backend pediu (gedeon:cnd:request no Redis db1), emite as CNDs no HOST
# (robô cnd_robot), salva os PDFs, registra em ged_certidoes (via container) e escreve o status.
set -uo pipefail
cd /opt/conecta-pro

exec 9>/tmp/gedeon_cnd_watcher.lock
flock -n 9 || exit 0   # já rodando

REDIS_PW=$(grep -E '^REDIS_PASSWORD=' .env | cut -d= -f2-)
RC() { docker exec conecta-pro-redis redis-cli -a "$REDIS_PW" --no-auth-warning -n 1 "$@" 2>/dev/null; }

REQ=$(RC GETDEL gedeon:cnd:request)
[ -z "$REQ" ] && exit 0

set -a; source .env; set +a   # TWOCAPTCHA_API_KEY
# Nó de saída (07/09/2026): Caixa bloqueia o IP da VPS na borda e o TST não responde a ele.
# Um PC fora daqui abre `ssh -N -R 127.0.0.1:1080 cndtunnel@82.25.75.74` (túnel reverso
# DINÂMICO do OpenSSH) e a porta 1080 vira um proxy SOCKS cuja saída é a internet DELE.
# Quando o túnel está de pé, o robô sai por lá; sem túnel, sai direto (SEFAZ/SEMEF funcionam).
if ss -ltn 2>/dev/null | grep -q '127.0.0.1:1080 '; then
    export CND_PROXY="socks5://127.0.0.1:1080"
    echo "[$(date '+%F %T')] nó de saída ativo — robô sai pelo túnel (127.0.0.1:1080)" >> /opt/conecta-pro/rotinas/cnd-watcher.log
fi
CNPJ=$(echo "$REQ" | python3 -c "import sys,json;print(json.load(sys.stdin).get('cnpj','35710481000103'))" 2>/dev/null || echo "35710481000103")
PORTAIS=$(echo "$REQ" | python3 -c "import sys,json;print(' '.join(json.load(sys.stdin).get('portais',['sefaz_am','cndt','prefeitura'])))" 2>/dev/null || echo "sefaz_am cndt prefeitura")

LOG="/tmp/cnd_emit_$(date +%Y%m%d_%H%M%S).log"
: > /opt/conecta-pro/uploads/cnd_results.jsonl   # limpa resultados anteriores

for P in $PORTAIS; do
    RC SET gedeon:cnd:status "{\"state\":\"running\",\"atual\":\"$P\",\"cnpj\":\"$CNPJ\"}" EX 1800 >/dev/null
    # Teto POR PORTAL. Os 400s uniformes matavam a Federal no meio do hCaptcha: medido em
    # 19/08/2026, ela encerrou sem imprimir JSON e sem erro no log — o watcher só grava
    # quando o robô devolve linha, então a certidão simplesmente não existia e nada dizia
    # por quê. A Receita resolve hCaptcha (3 tentativas internas) e ainda baixa o PDF; a
    # SEMEF e a Sefaz-AM fecham em muito menos.
    case "$P" in
        federal) TETO=900 ;;
        *)       TETO=400 ;;
    esac
    # TST e Caixa mudaram de cara e só saem pelo nó de saída: robô próprio (cnd_robo2.py,
    # 07/09/2026), mesmo contrato de saída. Os demais seguem no cnd_robot.py.
    case "$P" in
        cndt|caixa) ROBO=backend/scripts/gedeon/cnd_robo2.py ;;
        *)          ROBO=backend/scripts/gedeon/cnd_robot.py ;;
    esac
    OUT=$(timeout "$TETO" python3 "$ROBO" "$P" "$CNPJ" 2>>"$LOG" | grep '^{' | tail -1)
    if [ -n "$OUT" ]; then
        echo "$OUT" >> /opt/conecta-pro/uploads/cnd_results.jsonl
    else
        # Silêncio aqui é indistinguível de sucesso na leitura de quem vê só o jsonl.
        # Deixa registrado que o portal foi tentado e não respondeu dentro do teto.
        echo "{\"portal\":\"$P\",\"cnpj\":\"$CNPJ\",\"ok\":false,\"situacao\":\"sem_resposta\",\"mensagem\":\"robô não devolveu resultado em ${TETO}s (teto do watcher)\"}" \
            >> /opt/conecta-pro/uploads/cnd_results.jsonl
        echo "[$(date '+%F %T')] $P/$CNPJ: sem resultado em ${TETO}s" >> "$LOG"
    fi
done

# registra em ged_certidoes (no container, que enxerga /app/uploads/cnd_results.jsonl + os PDFs)
cp backend/scripts/gedeon/register_cnds.py uploads/_register_cnds.py
docker exec -w /app -e PYTHONPATH=/app conecta-pro-backend python /app/uploads/_register_cnds.py >> "$LOG" 2>&1 || true
rm -f uploads/_register_cnds.py

RC SET gedeon:cnd:status "{\"state\":\"done\",\"cnpj\":\"$CNPJ\",\"ts\":\"$(date -u +%FT%TZ)\"}" EX 1800 >/dev/null
echo "[$(date '+%F %T')] CND emissão concluída p/ $CNPJ ($PORTAIS)" >> "$LOG"
