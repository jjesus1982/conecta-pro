"""Análise de Riscos Jurídicos (trabalhista + tributário) — endpoints.

Rotas sob /juridico/riscos. Lê DADO REAL do banco (employees, contracts, nfses,
sst_afastamentos, gp_clock_punches). Nada é fabricado — o que não se deriva do
dado real vem rotulado como "requer análise"/"validar com contador".

Padrão consistente com o resto do módulo Jurídico (get_sync_db_dependency, sync).
Autenticação via CurrentActiveUser (mesmo dependency do core/auth).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.auth.dependencies import get_current_active_user
from core.database.session import get_sync_db_dependency

from . import riscos_service as svc

router = APIRouter(prefix="/juridico/riscos", tags=["Jurídico - Riscos"])


@router.get("/dashboard", summary="Painel de riscos (trabalhista + tributário) — resumo")
def dashboard(
    db: Session = Depends(get_sync_db_dependency),
    current_user=Depends(get_current_active_user),
) -> dict:
    return svc.dashboard_riscos(db)


@router.get("/trabalhista", summary="Risco trabalhista — exposição de passivo (estimativa)")
def trabalhista(
    db: Session = Depends(get_sync_db_dependency),
    current_user=Depends(get_current_active_user),
) -> dict:
    return svc.riscos_trabalhista(db)


@router.get("/tributario", summary="Risco tributário — enquadramento/carga/retenções")
def tributario(
    db: Session = Depends(get_sync_db_dependency),
    current_user=Depends(get_current_active_user),
) -> dict:
    return svc.riscos_tributario(db)
