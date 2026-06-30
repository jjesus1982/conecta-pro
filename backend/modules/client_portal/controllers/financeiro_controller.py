"""Portal do Cliente — Financeiro (NFS-e, contrato, boletos)."""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from modules.client_portal.middleware.portal_auth import get_current_portal_client
from modules.client_portal.services import portal_financeiro_service as svc

router = APIRouter(prefix="/financeiro", tags=["Portal - Financeiro"])


@router.get("/resumo")
async def resumo(client_id: str = Depends(get_current_portal_client), db: AsyncSession = Depends(get_db)) -> Any:
    return await svc.resumo(db, client_id)


@router.get("/notas")
async def notas(client_id: str = Depends(get_current_portal_client), db: AsyncSession = Depends(get_db)) -> Any:
    return await svc.notas(db, client_id)


@router.get("/contrato")
async def contrato(client_id: str = Depends(get_current_portal_client), db: AsyncSession = Depends(get_db)) -> Any:
    return await svc.contrato(db, client_id)


@router.get("/boletos")
async def boletos(client_id: str = Depends(get_current_portal_client), db: AsyncSession = Depends(get_db)) -> Any:
    return await svc.boletos(db, client_id)
