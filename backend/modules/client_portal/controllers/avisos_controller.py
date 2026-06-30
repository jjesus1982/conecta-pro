"""Portal do Cliente — Caixa de avisos (notificações proativas do José Luís)."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from modules.client_portal.middleware.portal_auth import get_current_portal_client
from modules.client_portal.services import portal_notify_service as svc

router = APIRouter(prefix="/avisos", tags=["Portal - Avisos"])


@router.get("")
async def listar(
    apenas_nao_lidas: bool = Query(False),
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    return {"avisos": await svc.listar(db, client_id, apenas_nao_lidas)}


@router.get("/nao-lidas")
async def nao_lidas(client_id: str = Depends(get_current_portal_client), db: AsyncSession = Depends(get_db)) -> Any:
    return {"nao_lidas": await svc.nao_lidas(db, client_id)}


@router.post("/{aviso_id}/lida")
async def marcar_lida(
    aviso_id: str,
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    ok = await svc.marcar_lida(db, client_id, aviso_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Aviso não encontrado")
    return {"ok": True}
