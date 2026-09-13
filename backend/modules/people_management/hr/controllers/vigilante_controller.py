"""Rotas DP — conformidade de vigilante (frente 05). Montado pelo aggregator do hr:
/api/v1/people-management/hr/vigilante/*. A regra vive em `services/conformidade_vigilante`."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.people_management.hr.schemas.vigilante import (
    CursoCreate,
    DevolucaoCreate,
    EntregaCreate,
    EquipamentoCreate,
    NomeDeGuerraUpdate,
)
from modules.people_management.hr.services import conformidade_vigilante as cv

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vigilante", tags=["DP - Vigilante (frente 05)"])


def _422(e: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("/aptidao", summary="Aptidão por pessoa (apto/inapto e o motivo)")
async def aptidao(
    current_user: CurrentActiveUser,
    escalados_hoje: bool = Query(False, description="Só quem está escalado hoje"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    itens = await cv.aptidao(db, so_escalados_hoje=escalados_hoje)
    sujeitos = [p for p in itens if p["sujeito"]]
    inaptos = [p for p in sujeitos if not p["apto"]]
    return {
        "hoje": cv.hoje_manaus(),
        "funcoes_exigem_credencial": await cv.funcoes_exigem_credencial(db),
        "total": len(itens),
        "sujeitos": len(sujeitos),
        "aptos": len(sujeitos) - len(inaptos),
        "inaptos": len(inaptos),
        "sem_dado": sum(1 for p in inaptos if any("sem" in m for m in p["motivos"])),
        "itens": itens,
    }


@router.get("/vencimentos", summary="Vence em 30/60/90 dias, vencidos e SEM DADO")
async def vencimentos(current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return await cv.vencimentos(db)


@router.get("/cursos", summary="Cursos/reciclagens cadastrados")
async def listar_cursos(
    current_user: CurrentActiveUser, employee_id: str | None = None, db: AsyncSession = Depends(get_db)
) -> list[dict]:
    return await cv.cursos(db, employee_id)


@router.post("/cursos", status_code=status.HTTP_201_CREATED, summary="Cadastrar curso/reciclagem concluído")
async def criar_curso(body: CursoCreate, current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        return await cv.cadastrar_curso(db, user_id=str(current_user.id), **body.model_dump())
    except ValueError as e:
        raise _422(e) from e


@router.get("/equipamentos", summary="Armamento e colete, com quem está cada um")
async def listar_equipamentos(current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await cv.posse_equipamentos(db)


@router.post("/equipamentos", status_code=status.HTTP_201_CREATED, summary="Cadastrar equipamento (série obrigatória)")
async def criar_equipamento(
    body: EquipamentoCreate, current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)
) -> dict:
    try:
        return await cv.cadastrar_equipamento(db, **body.model_dump())
    except ValueError as e:
        raise _422(e) from e


@router.post("/equipamentos/{equipamento_id}/entregar", summary="Entrega datada a um responsável")
async def entregar(
    equipamento_id: str, body: EntregaCreate, current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)
) -> dict:
    try:
        return await cv.entregar(
            db,
            equipamento_id=equipamento_id,
            employee_id=str(body.employee_id),
            user_id=str(current_user.id),
            observacao=body.observacao,
        )
    except ValueError as e:
        raise _422(e) from e


@router.post("/equipamentos/{equipamento_id}/devolver", summary="Devolução datada")
async def devolver(
    equipamento_id: str,
    current_user: CurrentActiveUser,
    body: DevolucaoCreate | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        return await cv.devolver(
            db,
            equipamento_id=equipamento_id,
            user_id=str(current_user.id),
            observacao=(body.observacao if body else None),
        )
    except ValueError as e:
        raise _422(e) from e


@router.patch("/employees/{employee_id}/nome-de-guerra", summary="Nome de guerra (identificação operacional)")
async def nome_de_guerra(
    employee_id: str, body: NomeDeGuerraUpdate, current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)
) -> dict:
    ok = await cv.definir_nome_de_guerra(db, employee_id=employee_id, nome_de_guerra=body.nome_de_guerra)
    if not ok:
        raise HTTPException(status_code=404, detail="funcionário não encontrado")
    return {"ok": True, "employee_id": employee_id, "nome_de_guerra": body.nome_de_guerra}
