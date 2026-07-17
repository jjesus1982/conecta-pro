#!/usr/bin/env bash
# =============================================================================
# Multi-CNPJ E2 — Classificação canônica dos contratos (e-mail Jordan 17/07)
# EXECUTAR SOMENTE COM O OK DO JORDAN. Cada migração persiste empresa_id e
# grava o aditivo de transferência (ContractAddendum) automaticamente.
# Uso: ./multicnpj_classificar_contratos.sh [--incluir-passaros]
# =============================================================================
set -euo pipefail

API="http://localhost:8080/api/v1"
SENHA=$(docker exec conecta-pro-mcp printenv ERP_PASSWORD)
TOKEN=$(curl -s -X POST "$API/auth/login" -H 'Content-Type: application/x-www-form-urlencoded' \
  -d "username=mcp-service@conectamais.pro&password=$SENHA" | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
U=$(grep -oP '^POSTGRES_USER=\K.*' /opt/conecta-pro/.env)

# → Patrimonial (mão de obra) — lista canônica do Jordan
PATRIMONIAL=(
  "CTR-2026-00008"  # Michelangelo — Limpeza + Serv. Gerais
  "CTR-2026-00010"  # Mirante das Flores — Portaria + Limpeza
  "CTR-2026-00011"  # Laranjeiras — Portaria
  "CTR-2026-00012"  # Prime Arena — Portaria + Limpeza + Piscina
  "CTR-2026-00013"  # Ideal Flores — Portaria + Serv. Gerais
  "CTR-2026-00007"  # Villa Dei Fiori — Portaria + Serv. Gerais
)
# ÚNICO CASO MISTO (Portaria + CFTV) — aguarda decisão do Jordan:
#   (a) migrar inteiro p/ Patrimonial (ela tem CNAE 8020-0/01) — use --incluir-passaros
#   (b) desmembrar em 2 contratos — tratar manualmente
if [[ "${1:-}" == "--incluir-passaros" ]]; then
  PATRIMONIAL+=("CTR-2026-00009")  # Villa dos Pássaros — Portaria + CFTV
fi

# Eletrônica: Gelain (00004), Parise (00005), Green Hills (00006) — já corretos
# pelo backfill; nada a fazer.

for NUM in "${PATRIMONIAL[@]}"; do
  CID=$(docker exec conecta-pro-postgres psql -U "$U" -d conecta_pro -Atc \
    "SELECT id FROM contracts WHERE contract_number='$NUM';")
  if [[ -z "$CID" ]]; then echo "AVISO: $NUM não encontrado"; continue; fi
  echo "== Migrando $NUM ($CID) → conecta_patrimonial =="
  curl -s -X POST "$API/empresas/migrador/executar" \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d "{\"contrato_id\":\"$CID\",\"empresa_origem_slug\":\"conecta_eletronica\",\"empresa_destino_slug\":\"conecta_patrimonial\"}" \
    | python3 -c 'import sys,json;d=json.load(sys.stdin);print(" ", d["mensagem"], "| aditivo:", d.get("aditivo_id"))'
done

echo "== Conferência final (oráculo) =="
docker exec conecta-pro-postgres psql -U "$U" -d conecta_pro -c \
  "SELECT e.slug, c.contract_number, cl.name FROM contracts c
   JOIN empresas e ON e.id=c.empresa_id LEFT JOIN clients cl ON cl.id=c.client_id
   WHERE c.status='active' ORDER BY e.slug, c.contract_number;"
