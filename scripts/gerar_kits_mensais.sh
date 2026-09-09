#!/bin/bash
# ──────────────────────────────────────────────────────────
# Geração automática de kits documentais mensais (kit do BANCO: ged_document_kits + ged_kit_documents)
# Executar: dia 1 de cada mês às 02:00
# Crontab:  0 2 1 * * /opt/conecta-pro/scripts/gerar_kits_mensais.sh
#
# 08/09/2026: parou de fazer login por HTTP com senha fixa (o login falhou TODO dia 1 de junho a setembro —
# "Falha ao obter token" — e ninguém viu). Agora roda o mesmo serviço do endpoint /ged/auto-assemble
# (KitBuilderService.auto_build_all_kits) DENTRO do container do backend: sem senha, sem rede, sem token.
# Se falhar, sai 1 e escreve o motivo no log; o oráculo test_oraculo_kits_mensais.py acusa no dia seguinte.
# ──────────────────────────────────────────────────────────
LOG="/var/log/conecta-pro/kits_mensais.log"
CONTAINER="conecta-pro-backend"
REF="${1:-$(date +%Y-%m-01)}"   # opcional: YYYY-MM-01 para refazer um mês
mkdir -p "$(dirname "$LOG")"
echo "$(date '+%Y-%m-%d %H:%M:%S') [START] Gerando kits de $REF" >> "$LOG"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] $CONTAINER não está de pé" >> "$LOG"; exit 1
fi

RESULT=$(docker exec -i -e PYTHONPATH=/app -w /app "$CONTAINER" python3 - "$REF" <<'PY' 2>>"$LOG"
import asyncio, json, sys
from datetime import date

async def main():
    ref = date.fromisoformat(sys.argv[1])
    from core.database import get_db
    from modules.people_management.ged.services.kit_builder_service import KitBuilderService
    gen = get_db(); db = await gen.__anext__()
    try:
        res = await KitBuilderService(db).auto_build_all_kits(ref)
        await db.commit()
        print(json.dumps(res, default=str))
    except Exception as exc:
        await db.rollback()
        print(json.dumps({"erro": str(exc)[:300]})); sys.exit(1)
    finally:
        try:
            await gen.aclose()
        except Exception:
            pass

asyncio.run(main())
PY
)
RC=$?
if [ $RC -ne 0 ] || echo "$RESULT" | grep -q '"erro"'; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] rc=$RC $RESULT" >> "$LOG"; exit 1
fi
KITS=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('kits_created', d.get('kits', d.get('total_kits', '?'))))" 2>/dev/null)
DOCS=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('documents_collected', d.get('documents', d.get('total_documents', '?'))))" 2>/dev/null)
echo "$(date '+%Y-%m-%d %H:%M:%S') [OK] $KITS kits, $DOCS documentos — $RESULT" >> "$LOG"
