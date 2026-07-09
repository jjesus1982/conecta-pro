"""Admin CCT Controller — CRUD de Convenção Coletiva de Trabalho.

Endpoints (prefixo /admin/cct):
  GET    /convencoes           — listar convenções
  POST   /convencoes           — criar convenção
  PUT    /convencoes/{id}      — atualizar convenção
  GET    /convencoes/{id}/cargos   — cargos da convenção
  POST   /convencoes/{id}/cargos   — adicionar cargo
  PUT    /cargos/{id}          — atualizar cargo
  GET    /convencoes/{id}/feriados  — feriados
  POST   /convencoes/{id}/feriados  — adicionar feriado
  DELETE /feriados/{id}        — remover feriado
  GET    /convencoes/{id}/beneficios — benefícios obrigatórios
  POST   /convencoes/{id}/beneficios — adicionar benefício
  GET    /convencao-vigente    — convenção vigente (leitura rápida)
"""

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.people_management.cct.repositories.cct_repository import CCTRepository
from modules.people_management.cct.schemas.cct_schemas import (
    CCTBeneficioCreate,
    CCTBeneficioResponse,
    CCTCargoCreate,
    CCTCargoResponse,
    CCTCargoUpdate,
    CCTConvencaoCreate,
    CCTConvencaoResponse,
    CCTConvencaoUpdate,
    CCTFeriadoCreate,
    CCTFeriadoResponse,
)
from modules.people_management.cct.services.cct_service import CCTService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/cct", tags=["Admin - CCT"])


# ─────────────────────────── CONVENÇÕES ───────────────────────────


@router.get("/convencoes", response_model=list[CCTConvencaoResponse])
async def listar_convencoes(current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)) -> Any:
    """Lista todas as convenções coletivas cadastradas."""
    repo = CCTRepository(db)
    return await repo.list_convencoes()


@router.get("/convencao-vigente", response_model=CCTConvencaoResponse | None)
async def get_convencao_vigente(current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)) -> Any:
    """Retorna a convenção vigente (is_vigente=True)."""
    repo = CCTRepository(db)
    return await repo.get_convencao_vigente()


@router.post("/convencoes", response_model=CCTConvencaoResponse, status_code=status.HTTP_201_CREATED)
async def criar_convencao(
    body: CCTConvencaoCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Cria nova convenção coletiva."""
    repo = CCTRepository(db)
    return await repo.create_convencao(body.model_dump())


@router.put("/convencoes/{convencao_id}", response_model=CCTConvencaoResponse)
async def atualizar_convencao(
    convencao_id: uuid.UUID,
    body: CCTConvencaoUpdate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Atualiza dados de uma convenção (ex: marcar como vigente)."""
    repo = CCTRepository(db)
    updated = await repo.update_convencao(convencao_id, body.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Convenção não encontrada.")
    return updated


# ─────────────────────────── CARGOS ───────────────────────────────


@router.get("/convencoes/{convencao_id}/cargos", response_model=list[CCTCargoResponse])
async def listar_cargos(
    convencao_id: uuid.UUID, current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)
) -> Any:
    """Lista cargos (pisos salariais) de uma convenção."""
    repo = CCTRepository(db)
    return await repo.get_cargos_by_convencao(convencao_id)


@router.post(
    "/convencoes/{convencao_id}/cargos",
    response_model=CCTCargoResponse,
    status_code=status.HTTP_201_CREATED,
)
async def adicionar_cargo(
    convencao_id: uuid.UUID,
    body: CCTCargoCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Adiciona cargo com piso salarial a uma convenção."""
    repo = CCTRepository(db)
    data = body.model_dump()
    data["convencao_id"] = convencao_id
    return await repo.create_cargo(data)


@router.put("/cargos/{cargo_id}", response_model=CCTCargoResponse)
async def atualizar_cargo(
    cargo_id: uuid.UUID,
    body: CCTCargoUpdate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Atualiza piso salarial ou adicionais de um cargo."""
    repo = CCTRepository(db)
    updated = await repo.update_cargo(cargo_id, body.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cargo não encontrado.")

    # Comunicação bidirecional: piso/adicional do cargo mudou → folha/SST/precificação reagem.
    try:
        from infrastructure.event_bus import EventTypes, event_bus

        await event_bus.emit(
            EventTypes.CCT_CARGO_ATUALIZADO,
            {
                "cct_cargo_id": str(cargo_id),
                "campos_alterados": list(body.model_dump(exclude_none=True).keys()),
            },
            source_module="cct",
        )
    except Exception:  # noqa: BLE001,S110
        pass
    return updated


# ─────────────────────────── FERIADOS ─────────────────────────────


@router.get("/convencoes/{convencao_id}/feriados", response_model=list[CCTFeriadoResponse])
async def listar_feriados(
    convencao_id: uuid.UUID,
    current_user: CurrentActiveUser,
    ano: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Lista feriados de uma convenção, opcionalmente filtrando por ano."""
    repo = CCTRepository(db)
    if ano:
        return await repo.get_feriados_by_ano(convencao_id, ano)
    return await repo.get_feriados_by_ano(convencao_id, 2026)


@router.post(
    "/convencoes/{convencao_id}/feriados",
    response_model=CCTFeriadoResponse,
    status_code=status.HTTP_201_CREATED,
)
async def adicionar_feriado(
    convencao_id: uuid.UUID,
    body: CCTFeriadoCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Adiciona feriado à convenção."""
    repo = CCTRepository(db)
    data = body.model_dump()
    data["convencao_id"] = convencao_id
    return await repo.create_feriado(data)


@router.delete("/feriados/{feriado_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_feriado(
    feriado_id: uuid.UUID, current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)
) -> None:
    """Remove feriado."""
    repo = CCTRepository(db)
    deleted = await repo.delete_feriado(feriado_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feriado não encontrado.")


# ─────────────────────────── BENEFÍCIOS ───────────────────────────


@router.get("/convencoes/{convencao_id}/beneficios", response_model=list[CCTBeneficioResponse])
async def listar_beneficios(
    convencao_id: uuid.UUID, current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)
) -> Any:
    """Lista benefícios obrigatórios de uma convenção."""
    repo = CCTRepository(db)
    return await repo.get_beneficios_obrigatorios(convencao_id)


@router.post(
    "/convencoes/{convencao_id}/beneficios",
    response_model=CCTBeneficioResponse,
    status_code=status.HTTP_201_CREATED,
)
async def adicionar_beneficio(
    convencao_id: uuid.UUID,
    body: CCTBeneficioCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Adiciona benefício obrigatório à convenção."""
    repo = CCTRepository(db)
    data = body.model_dump()
    data["convencao_id"] = convencao_id
    return await repo.create_beneficio(data)


# ─────────────────────────── CACHE ────────────────────────────────


@router.post("/cache/invalidar", status_code=status.HTTP_200_OK)
async def invalidar_cache_cct(current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)) -> dict:
    """Invalida todo o cache CCT no Redis (usar após atualizações)."""
    service = CCTService(db)
    await service.invalidar_cache()
    return {"message": "Cache CCT invalidado com sucesso."}


# ── Gate module:dp (padrão modules/financeiro/__init__.py) ──────────────────
# Router admin CCT montado DIRETO no main (fora do aggregator people_management).
from core.permissions import requer_modulo as _requer_modulo  # noqa: E402

_dep_dp = _requer_modulo("dp")
for _route in router.routes:
    _route.dependencies.append(_dep_dp)
