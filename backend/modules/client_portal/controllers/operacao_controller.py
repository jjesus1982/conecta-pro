"""Portal do Cliente — Raio-X da Operação (endpoints).

O condomínio vê, com total transparência, as pessoas e a operação da Conecta Mais
alocadas nele. Tudo escopado ao cliente autenticado.
"""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from modules.client_portal.middleware.portal_auth import get_current_portal_client
from modules.client_portal.services import portal_operacao_service as svc

router = APIRouter(prefix="/operacao", tags=["Portal - Raio-X da Operacao"])


@router.get("/resumo")
async def resumo(client_id: str = Depends(get_current_portal_client), db: AsyncSession = Depends(get_db)) -> Any:
    return await svc.resumo(db, client_id)


@router.get("/equipe")
async def equipe(client_id: str = Depends(get_current_portal_client), db: AsyncSession = Depends(get_db)) -> Any:
    return await svc.equipe(db, client_id)


@router.get("/assiduidade")
async def assiduidade(
    competencia: str | None = Query(None, description="YYYY-MM"),
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    return await svc.assiduidade(db, client_id, competencia)


@router.get("/ranking")
async def ranking(client_id: str = Depends(get_current_portal_client), db: AsyncSession = Depends(get_db)) -> Any:
    return await svc.ranking(db, client_id)


@router.get("/atestados")
async def atestados(client_id: str = Depends(get_current_portal_client), db: AsyncSession = Depends(get_db)) -> Any:
    return await svc.atestados(db, client_id)


@router.get("/turnover")
async def turnover(
    meses: int = Query(12, ge=1, le=36),
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    return await svc.turnover(db, client_id, meses)


@router.get("/advertencias")
async def advertencias(client_id: str = Depends(get_current_portal_client), db: AsyncSession = Depends(get_db)) -> Any:
    return await svc.advertencias(db, client_id)


@router.get("/escalas")
async def escalas(
    competencia: str | None = Query(None, description="YYYY-MM"),
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    return await svc.escalas(db, client_id, competencia)
