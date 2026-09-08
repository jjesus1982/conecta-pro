"""Controller FastAPI — FASE 4 BLOCO 3 / T2 (§27, §28).

Expõe KitBuilderService via 2 endpoints:
- GET /kits/completude/{condominio_id}?mes_ref=MM.YYYY
- GET /kits/lote?mes_ref=MM.YYYY

§27: contrato de API (fonte única da verdade)
§28: documentação desta implementação

§13.1 Chesterton: KitBuilderService usado como está, sem alteração.
BUG 7 (CPRO 9): auth via Depends(get_current_user) OBRIGATÓRIA em ambos endpoints.
§28.6: usa get_sync_db_dependency (sync) pois KitBuilderService usa Session síncrona.
"""

from __future__ import annotations


from fastapi import APIRouter, Query


router = APIRouter(prefix="/gedeon", tags=["GEDEON — Kits"])

MES_REF_QUERY = Query(
    ...,
    description="Mês de referência no formato MM.YYYY (ex: 03.2026)",
    regex=r"^(0[1-9]|1[0-2])\.\d{4}$",
    examples=["03.2026"],
)


