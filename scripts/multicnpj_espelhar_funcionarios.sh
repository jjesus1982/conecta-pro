#!/usr/bin/env bash
# =============================================================================
# Multi-CNPJ E3 — ESPELHAMENTO da transição trabalhista executada pela PORTTE
# Roda SOMENTE quando a Portte confirmar a transferência (até 25/07) e o Jordan
# autorizar, informando a COMPETÊNCIA oficial da sucessão.
#
# O que faz (espelhar, não assumir — pré-mortem F2):
#   1. employees ativos (CLT) -> empresa_id = Patrimonial
#   2. Define MULTICNPJ_FRONTEIRA_COMPETENCIA nos DOIS .env (regra anti-
#      reescrita: holerites de competências anteriores ficam CNPJ1 p/ sempre)
#   3. Oráculo de conferência + lembrete do recreate
#
# Uso: ./multicnpj_espelhar_funcionarios.sh 2026-07   (competência YYYY-MM)
# =============================================================================
set -euo pipefail

FRONTEIRA="${1:?Informe a competência oficial da Portte (ex.: 2026-07)}"
[[ "$FRONTEIRA" =~ ^20[0-9]{2}-(0[1-9]|1[0-2])$ ]] || { echo "Competência inválida: $FRONTEIRA"; exit 1; }

U=$(grep -oP '^POSTGRES_USER=\K.*' /opt/conecta-pro/.env)
PATRIMONIAL_ID="7d79ed12-d480-4906-b2e0-2b2c4d299bab"
TS=$(date +%Y%m%d_%H%M%S)

echo "== Snapshot de segurança =="
docker exec conecta-pro-postgres pg_dump -U "$U" conecta_pro -t employees -t hr_payslips \
  | gzip > "/opt/conecta-pro/backups/postgresql/pre_espelhamento_${TS}.sql.gz"
gunzip -t "/opt/conecta-pro/backups/postgresql/pre_espelhamento_${TS}.sql.gz" && echo OK

echo "== Flip: vínculos VIGENTES -> Patrimonial (ativo + afastado_inss + suspenso;"
echo "   demitidos/inativos ficam no histórico CNPJ1) =="
docker exec conecta-pro-postgres psql -U "$U" -d conecta_pro -c "
UPDATE employees SET empresa_id = '$PATRIMONIAL_ID', updated_at = NOW()
WHERE LOWER(COALESCE(status::text,'')) IN ('ativo','afastado_inss','suspenso')
  AND COALESCE(is_homologacao, false) = false;
-- Pós-flip: CLT NOVO nasce na Patrimonial (era Eletrônica até a virada)
ALTER TABLE employees ALTER COLUMN empresa_id SET DEFAULT '$PATRIMONIAL_ID';
ALTER TABLE hr_payslips ALTER COLUMN empresa_id SET DEFAULT '$PATRIMONIAL_ID';"

echo "== Fronteira anti-reescrita = $FRONTEIRA (holerites < fronteira ficam CNPJ1) =="
for F in /opt/conecta-pro/.env /opt/conecta-pro/backend/.env; do
  sed -i "s/^MULTICNPJ_FRONTEIRA_COMPETENCIA=.*/MULTICNPJ_FRONTEIRA_COMPETENCIA=$FRONTEIRA/" "$F"
  grep "^MULTICNPJ_FRONTEIRA_COMPETENCIA" "$F"
done

echo "== Oráculo =="
docker exec conecta-pro-postgres psql -U "$U" -d conecta_pro -c "
SELECT e.slug, emp.status, count(*) FROM employees emp
JOIN empresas e ON e.id = emp.empresa_id GROUP BY 1,2 ORDER BY 1,2;"

echo ""
echo "LEMBRETES OBRIGATÓRIOS:"
echo "  1. Env só vale após: docker compose up -d --force-recreate backend"
echo "     (CHECAR /tmp/conecta_deploy.lock e container green ANTES)"
echo "  2. Gate anti-reescrita: re-renderizar holerite de competência ANTERIOR"
echo "     à fronteira e conferir que sai CNPJ1 byte-idêntico"
echo "  3. Conferir com a planilha/retorno da Portte: CPF × empregador × data"
