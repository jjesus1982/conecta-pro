#!/usr/bin/env bash
# GEDEON — Ponto assinado mensal (Sólides/Tangerino) em UM comando.
# Part 1 (HOST, Playwright): loga como Pyetra, baixa os espelhos ASSINADOS -> uploads/solides_espelhos/.
# Part 2 (CONTAINER): mapeia funcionário->condomínio (via Folha de Pagamento.pdf do kit) e arquiva
#   "Folha de Ponto Assinada_*.pdf" no kit do condomínio.
# Playwright só roda no host; o gdrive/DB só no container — por isso o flow é híbrido. Idempotente.
#
# Competência: argumento $1 = MM.YYYY. Sem argumento, usa o MÊS ANTERIOR (alinha com o orquestrador,
# salário em arrears). Janela de assinatura derivada: 20/(mês-1) até último dia da competência.
set -euo pipefail
cd /opt/conecta-pro

if [ "${1:-}" != "" ]; then
    COMP="$1"
else
    COMP=$(python3 -c "from datetime import date; h=date.today(); m=h.month-1; a=h.year; m,a=(12,a-1) if m<1 else (m,a); print(f'{m:02d}.{a}')")
fi
# janela de datas (DD/MM/AAAA) p/ Part 1: 20 do mês anterior à competência -> último dia da competência
read DT_INI DT_FIM < <(python3 -c "
import calendar
mm,yy='$COMP'.split('.'); mm=int(mm); yy=int(yy)
pm,py=(12,yy-1) if mm-1<1 else (mm-1,yy)
ult=calendar.monthrange(yy,mm)[1]
print(f'20/{pm:02d}/{py} {ult:02d}/{mm:02d}/{yy}')
")

LOG="/tmp/ponto_assinado_$(date +%Y%m%d_%H%M%S).log"
echo "[$(date '+%F %T')] GEDEON ponto assinado — competência $COMP | janela $DT_INI-$DT_FIM" | tee "$LOG"

# ── Part 1: HOST (Playwright) ──────────────────────────────────────────────────
echo "[$(date '+%F %T')] Part 1 (host): baixando espelhos assinados..." | tee -a "$LOG"
python3 backend/scripts/gedeon/solides_espelho_robot.py "$DT_INI" "$DT_FIM" >> "$LOG" 2>&1 || {
    echo "[ERRO] Part 1 falhou — ver $LOG" | tee -a "$LOG"; exit 1; }
N=$(python3 -c "import json;print(len(json.load(open('uploads/solides_espelhos/manifesto.json'))))" 2>/dev/null || echo 0)
echo "[$(date '+%F %T')] Part 1 OK — $N espelhos no manifesto" | tee -a "$LOG"

# ── Part 1b: HOST — GED do Sólides (VT/VR, férias, 13º assinados via API REST) ──
# Robusto: Playwright só p/ pegar o token; baixa os PDFs assinados (signedUrl S3).
echo "[$(date '+%F %T')] Part 1b (host): baixando assinados do GED (VT/VR, férias)..." | tee -a "$LOG"
# passa a competência: o VT/VR entra pela REF do mês trabalhado (não o mais recente, que é adiantado)
python3 backend/scripts/gedeon/solides_ged_robot.py "$COMP" >> "$LOG" 2>&1 || \
    echo "[AVISO] GED do Sólides falhou (segue sem) — ver $LOG" | tee -a "$LOG"

# ── Part 2: CONTAINER (gdrive + DB) ────────────────────────────────────────────
# uploads/ é volume montado -> o container vê o script em /app/uploads/_part2_espelho.py.
# PYTHONPATH=/app p/ o pacote `core`/`modules` resolver fora do workdir do script.
echo "[$(date '+%F %T')] Part 2 (container): mapeando -> kit..." | tee -a "$LOG"
cp backend/scripts/gedeon/solides_espelho_part2_mapear.py uploads/_part2_espelho.py
docker exec -w /app -e PYTHONPATH=/app conecta-pro-backend \
    python /app/uploads/_part2_espelho.py "$COMP" >> "$LOG" 2>&1 || {
    echo "[ERRO] Part 2 (ponto) falhou — ver $LOG" | tee -a "$LOG"; rm -f uploads/_part2_espelho.py; exit 1; }
rm -f uploads/_part2_espelho.py
# Part 2b: arquiva os documentos do GED (VT/VR, férias) nos kits
cp backend/scripts/gedeon/solides_ged_part2.py uploads/_ged_part2.py
docker exec -w /app -e PYTHONPATH=/app conecta-pro-backend \
    python /app/uploads/_ged_part2.py "$COMP" >> "$LOG" 2>&1 || \
    echo "[AVISO] Part 2b (GED) falhou — ver $LOG" | tee -a "$LOG"
rm -f uploads/_ged_part2.py
echo "[$(date '+%F %T')] Concluído. Resumo:" | tee -a "$LOG"
grep -E "competencia:|arquivados:|<-" "$LOG" | tail -20 | tee -a "$LOG"
echo "[$(date '+%F %T')] GEDEON ponto assinado — fim. Log: $LOG" | tee -a "$LOG"
