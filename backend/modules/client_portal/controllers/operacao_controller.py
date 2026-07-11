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


@router.get("/ocorrencias")
async def ocorrencias(client_id: str = Depends(get_current_portal_client), db: AsyncSession = Depends(get_db)) -> Any:
    """Ocorrências não-sensíveis do condomínio (incidentes/manutenção/elogios)."""
    return await svc.ocorrencias(db, client_id)


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


# ── Visitas de gestão (rondas de inspeção) — prova de serviço prestado ────────


@router.get("/visitas")
async def visitas(
    limite: int = Query(10, ge=1, le=50),
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Últimas visitas da gestão Conecta ao condomínio (sanitizadas, com fotos)."""
    from modules.client_portal.services import portal_visitas_service

    return await portal_visitas_service.visitas(db, client_id, limite)


@router.get("/visitas/{round_id}/checkpoints/{checkpoint_id}/fotos/{nome}")
async def foto_visita(
    round_id: str,
    checkpoint_id: str,
    nome: str,
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
):
    """Foto de evidência da visita — validada na cadeia cliente→posto→checkpoint."""
    import uuid as _uuid

    from fastapi import HTTPException
    from fastapi.responses import FileResponse

    from modules.client_portal.services import portal_visitas_service

    try:
        _uuid.UUID(round_id), _uuid.UUID(checkpoint_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Foto não encontrada.")
    alvo = await portal_visitas_service.foto_autorizada(db, client_id, round_id, checkpoint_id, nome)
    if alvo is None:
        raise HTTPException(status_code=404, detail="Foto não encontrada.")
    return FileResponse(alvo)
