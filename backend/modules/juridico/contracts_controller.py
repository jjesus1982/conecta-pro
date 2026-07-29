"""Central de Contratos (Jurídico) — endpoints consolidados + alertas.

Base do módulo Jurídico do Conecta PRO. Lê dado REAL da tabela contracts.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.auth.dependencies import get_current_active_user
from core.database.session import get_sync_db_dependency
from modules.ai.contract_analysis.services.analise_contrato import analisar as analisar_texto_contrato

from . import contracts_service as svc

router = APIRouter(prefix="/juridico/contratos", tags=["Jurídico - Central de Contratos"])


@router.get("/dashboard", summary="Painel da Central de Contratos (totais + alertas reais)")
def dashboard(db: Session = Depends(get_sync_db_dependency)) -> dict:
    return svc.dashboard_contratos(db)


@router.get("/alertas", summary="Só os alertas (vencimento/renovação/reajuste/assinatura)")
def alertas(db: Session = Depends(get_sync_db_dependency)) -> dict:
    d = svc.dashboard_contratos(db)
    return {"referencia": d["referencia"], "total": len(d["alertas"]), "alertas": d["alertas"]}


@router.get("/{contrato_id}", summary="Detalhe de um contrato + alertas")
def detalhe(contrato_id: str, db: Session = Depends(get_sync_db_dependency)) -> dict:
    c = svc.obter_contrato(db, contrato_id)
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    return c


@router.get("", summary="Lista consolidada de contratos com status de alerta")
def listar(db: Session = Depends(get_sync_db_dependency)) -> dict:
    return svc.listar_contratos(db)


@router.get(
    "/{contrato_id}/analise",
    summary="Análise read-only do contrato (cláusulas/risco/compliance por regex+scoring)",
)
async def analise(
    contrato_id: str,
    db: Session = Depends(get_sync_db_dependency),
    current_user=Depends(get_current_active_user),
) -> dict:
    c = svc.obter_texto_contrato(db, contrato_id)
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    resultado = await analisar_texto_contrato(c["texto"])
    return {"id": c["id"], "numero": c["numero"], "nome": c["nome"], **resultado}
