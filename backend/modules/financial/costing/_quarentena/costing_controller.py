"""Costing Controllers - Endpoints REST para Custeio ABC."""

import logging
from datetime import date
from datetime import datetime as dt
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user, require_permissions
from core.database import get_db
from modules.financial.costing.models import CostAnalysis
from modules.financial.costing.repositories import (
    CostActivityRepository,
    CostAllocationRepository,
    CostAnalysisRepository,
    CostDriverRepository,
    CostObjectRepository,
    CostPoolRepository,
)
from modules.financial.costing.schemas import (
    ABCDashboard,
    AllocationSummary,
    # Cost Activity
    CostActivityCreate,
    CostActivityFilter,
    CostActivityResponse,
    CostActivityUpdate,
    CostAllocationApprove,
    CostAllocationBatch,
    # Cost Allocation
    CostAllocationCreate,
    CostAllocationFilter,
    CostAllocationResponse,
    CostAllocationReverse,
    CostAnalysisFilter,
    # Cost Analysis
    CostAnalysisResponse,
    CostAnalysisRun,
    # Cost Driver
    CostDriverCreate,
    CostDriverFilter,
    CostDriverResponse,
    CostDriverUpdate,
    # Statistics
    CostingStats,
    CostObjectAddDirectCost,
    # Cost Object
    CostObjectCreate,
    CostObjectFilter,
    CostObjectResponse,
    CostObjectUpdate,
    CostPoolAddCost,
    # Cost Pool
    CostPoolCreate,
    CostPoolFilter,
    CostPoolResponse,
    CostPoolUpdate,
    CostTrend,
)
from modules.financial.costing.services import (
    ABCService,
    AllocationService,
    CostAIService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/costing", tags=["Costing - Custeio ABC"])


# ============================================================
# COST DRIVER ENDPOINTS
# ============================================================


@router.get("/drivers", response_model=list[CostDriverResponse])
async def list_drivers(
    condominio_id: UUID | None = None,
    codigo: str | None = None,
    nome: str | None = None,
    tipo: str | None = None,
    status: str | None = None,
    ativo: bool | None = True,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[CostDriverResponse]:
    """Lista cost drivers com filtros."""
    repo = CostDriverRepository(db)
    filters = CostDriverFilter(
        condominio_id=condominio_id or current_user.condominio_id,
        codigo=codigo,
        nome=nome,
        tipo=tipo,
        status=status,
        ativo=ativo,
    )
    drivers = await repo.get_multi(filters=filters, skip=skip, limit=limit)
    return [CostDriverResponse.model_validate(d) for d in drivers]


@router.post(
    "/drivers",
    response_model=CostDriverResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_driver(
    data: CostDriverCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permissions(["costing.create"])),
) -> CostDriverResponse:
    """Cria novo cost driver."""
    repo = CostDriverRepository(db)

    if not data.condominio_id:
        data.condominio_id = current_user.condominio_id

    driver = await repo.create(data)
    await db.commit()

    logger.info(f"Cost Driver criado: {driver.id} por {current_user.id}")
    return CostDriverResponse.model_validate(driver)


@router.get("/drivers/{driver_id}", response_model=CostDriverResponse)
async def get_driver(  # pylint: disable=unused-argument
    driver_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> CostDriverResponse:
    """Obtém cost driver por ID."""
    repo = CostDriverRepository(db)
    driver = await repo.get(driver_id)
    if not driver:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Cost Driver {driver_id} não encontrado"
        )
    return CostDriverResponse.model_validate(driver)


@router.patch("/drivers/{driver_id}", response_model=CostDriverResponse)
async def update_driver(
    driver_id: UUID,
    data: CostDriverUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permissions(["costing.update"])),
) -> CostDriverResponse:
    """Atualiza cost driver."""
    repo = CostDriverRepository(db)
    driver = await repo.update(driver_id, data)  # pylint: disable=too-many-function-args
    if not driver:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Cost Driver {driver_id} não encontrado"
        )
    await db.commit()

    logger.info(f"Cost Driver atualizado: {driver_id} por {current_user.id}")
    return CostDriverResponse.model_validate(driver)


@router.delete("/drivers/{driver_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_driver(
    driver_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permissions(["costing.delete"])),
) -> None:
    """Remove cost driver (soft delete)."""
    repo = CostDriverRepository(db)
    success = await repo.soft_delete(driver_id)
    if not success:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Cost Driver {driver_id} não encontrado"
        )
    await db.commit()
    logger.info(f"Cost Driver removido: {driver_id} por {current_user.id}")


@router.get("/drivers/stats", response_model=dict)
async def get_driver_stats(
    condominio_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """Obtém estatísticas dos cost drivers."""
    repo = CostDriverRepository(db)
    stats = await repo.get_statistics(condominio_id=condominio_id or current_user.condominio_id)
    return stats


# ============================================================
# COST ACTIVITY ENDPOINTS
# ============================================================


@router.get("/activities", response_model=list[CostActivityResponse])
async def list_activities(
    condominio_id: UUID | None = None,
    codigo: str | None = None,
    nome: str | None = None,
    nivel: str | None = None,
    status: str | None = None,
    ativo: bool | None = True,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[CostActivityResponse]:
    """Lista atividades de custo com filtros."""
    repo = CostActivityRepository(db)
    filters = CostActivityFilter(
        condominio_id=condominio_id or current_user.condominio_id,
        codigo=codigo,
        nome=nome,
        nivel=nivel,
        status=status,
        ativo=ativo,
    )
    activities = await repo.get_multi(filters=filters, skip=skip, limit=limit)
    return [CostActivityResponse.model_validate(a) for a in activities]


@router.post(
    "/activities",
    response_model=CostActivityResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_activity(
    data: CostActivityCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permissions(["costing.create"])),
) -> CostActivityResponse:
    """Cria nova atividade de custo."""
    repo = CostActivityRepository(db)

    if not data.condominio_id:
        data.condominio_id = current_user.condominio_id

    activity = await repo.create(data)
    await db.commit()

    logger.info(f"Cost Activity criada: {activity.id} por {current_user.id}")
    return CostActivityResponse.model_validate(activity)


@router.get("/activities/{activity_id}", response_model=CostActivityResponse)
async def get_activity(  # pylint: disable=unused-argument
    activity_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> CostActivityResponse:
    """Obtém atividade por ID."""
    repo = CostActivityRepository(db)
    activity = await repo.get(activity_id)
    if not activity:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Cost Activity {activity_id} não encontrada"
        )
    return CostActivityResponse.model_validate(activity)


@router.patch("/activities/{activity_id}", response_model=CostActivityResponse)
async def update_activity(
    activity_id: UUID,
    data: CostActivityUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permissions(["costing.update"])),
) -> CostActivityResponse:
    """Atualiza atividade de custo."""
    repo = CostActivityRepository(db)
    # pylint: disable=too-many-function-args
    activity = await repo.update(activity_id, data)
    if not activity:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Cost Activity {activity_id} não encontrada"
        )
    await db.commit()

    logger.info(f"Cost Activity atualizada: {activity_id} por {current_user.id}")
    return CostActivityResponse.model_validate(activity)


@router.delete("/activities/{activity_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_activity(
    activity_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permissions(["costing.delete"])),
) -> None:
    """Remove atividade (soft delete)."""
    repo = CostActivityRepository(db)
    success = await repo.soft_delete(activity_id)
    if not success:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Cost Activity {activity_id} não encontrada"
        )
    await db.commit()
    logger.info(f"Cost Activity removida: {activity_id} por {current_user.id}")


# ============================================================
# COST POOL ENDPOINTS
# ============================================================


@router.get("/pools", response_model=list[CostPoolResponse])
async def list_pools(
    condominio_id: UUID | None = None,
    codigo: str | None = None,
    nome: str | None = None,
    tipo: str | None = None,
    status: str | None = None,
    ativo: bool | None = True,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[CostPoolResponse]:
    """Lista pools de custo com filtros."""
    repo = CostPoolRepository(db)
    filters = CostPoolFilter(
        condominio_id=condominio_id or current_user.condominio_id,
        codigo=codigo,
        nome=nome,
        tipo=tipo,
        status=status,
        ativo=ativo,
    )
    pools = await repo.get_multi(filters=filters, skip=skip, limit=limit)
    return [CostPoolResponse.model_validate(p) for p in pools]


@router.post("/pools", response_model=CostPoolResponse, status_code=http_status.HTTP_201_CREATED)
async def create_pool(
    data: CostPoolCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permissions(["costing.create"])),
) -> CostPoolResponse:
    """Cria novo pool de custo."""
    repo = CostPoolRepository(db)

    if not data.condominio_id:
        data.condominio_id = current_user.condominio_id

    pool = await repo.create(data)
    await db.commit()

    logger.info(f"Cost Pool criado: {pool.id} por {current_user.id}")
    return CostPoolResponse.model_validate(pool)


@router.get("/pools/{pool_id}", response_model=CostPoolResponse)
async def get_pool(  # pylint: disable=unused-argument
    pool_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> CostPoolResponse:
    """Obtém pool por ID."""
    repo = CostPoolRepository(db)
    pool = await repo.get(pool_id)
    if not pool:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Cost Pool {pool_id} não encontrado")
    return CostPoolResponse.model_validate(pool)


@router.patch("/pools/{pool_id}", response_model=CostPoolResponse)
async def update_pool(
    pool_id: UUID,
    data: CostPoolUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permissions(["costing.update"])),
) -> CostPoolResponse:
    """Atualiza pool de custo."""
    repo = CostPoolRepository(db)
    # pylint: disable=too-many-function-args
    pool = await repo.update(pool_id, data)
    if not pool:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Cost Pool {pool_id} não encontrado")
    await db.commit()

    logger.info(f"Cost Pool atualizado: {pool_id} por {current_user.id}")
    return CostPoolResponse.model_validate(pool)


@router.delete("/pools/{pool_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_pool(
    pool_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permissions(["costing.delete"])),
) -> None:
    """Remove pool (soft delete)."""
    repo = CostPoolRepository(db)
    success = await repo.soft_delete(pool_id)
    if not success:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Cost Pool {pool_id} não encontrado")
    await db.commit()
    logger.info(f"Cost Pool removido: {pool_id} por {current_user.id}")


@router.post("/pools/{pool_id}/add-cost", response_model=CostPoolResponse, status_code=201)
async def add_cost_to_pool(  # pylint: disable=unused-argument
    pool_id: UUID,
    data: CostPoolAddCost,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permissions(["costing.update"])),
) -> CostPoolResponse:
    """Adiciona custo a um pool."""
    repo = CostPoolRepository(db)
    pool = await repo.add_cost(pool_id, data.valor, data.descricao)
    if not pool:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Cost Pool {pool_id} não encontrado")
    await db.commit()

    logger.info(f"Custo adicionado ao pool {pool_id}: R$ {data.valor}")
    return CostPoolResponse.model_validate(pool)


@router.get("/pools/{pool_id}/distribution")
async def get_pool_distribution(  # pylint: disable=unused-argument
    pool_id: UUID,
    periodo_inicio: date = Query(...),
    periodo_fim: date = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """Obtém distribuição de custos do pool para atividades."""
    service = ABCService(db)
    return await service.get_pool_distribution(pool_id, periodo_inicio, periodo_fim)


# ============================================================
# COST OBJECT ENDPOINTS
# ============================================================


@router.get("/objects", response_model=list[CostObjectResponse])
async def list_objects(
    condominio_id: UUID | None = None,
    codigo: str | None = None,
    nome: str | None = None,
    tipo: str | None = None,
    lucrativo: bool | None = None,
    ativo: bool | None = True,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[CostObjectResponse]:
    """Lista objetos de custo com filtros."""
    repo = CostObjectRepository(db)
    filters = CostObjectFilter(
        condominio_id=condominio_id or current_user.condominio_id,
        codigo=codigo,
        nome=nome,
        tipo=tipo,
        lucrativo=lucrativo,
        ativo=ativo,
    )
    objects = await repo.get_multi(filters=filters, skip=skip, limit=limit)
    return [CostObjectResponse.model_validate(o) for o in objects]


@router.post(
    "/objects",
    response_model=CostObjectResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_object(
    data: CostObjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permissions(["costing.create"])),
) -> CostObjectResponse:
    """Cria novo objeto de custo."""
    repo = CostObjectRepository(db)

    if not data.condominio_id:
        data.condominio_id = current_user.condominio_id

    obj = await repo.create(data)
    await db.commit()

    logger.info(f"Cost Object criado: {obj.id} por {current_user.id}")
    return CostObjectResponse.model_validate(obj)


@router.get("/objects/{object_id}", response_model=CostObjectResponse)
async def get_object(  # pylint: disable=unused-argument
    object_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> CostObjectResponse:
    """Obtém objeto de custo por ID."""
    repo = CostObjectRepository(db)
    obj = await repo.get(object_id)
    if not obj:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Cost Object {object_id} não encontrado"
        )
    return CostObjectResponse.model_validate(obj)


@router.patch("/objects/{object_id}", response_model=CostObjectResponse)
async def update_object(
    object_id: UUID,
    data: CostObjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permissions(["costing.update"])),
) -> CostObjectResponse:
    """Atualiza objeto de custo."""
    repo = CostObjectRepository(db)
    # pylint: disable=too-many-function-args
    obj = await repo.update(object_id, data)
    if not obj:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Cost Object {object_id} não encontrado"
        )
    await db.commit()

    logger.info(f"Cost Object atualizado: {object_id} por {current_user.id}")
    return CostObjectResponse.model_validate(obj)


@router.delete("/objects/{object_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_object(
    object_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permissions(["costing.delete"])),
) -> None:
    """Remove objeto de custo (soft delete)."""
    repo = CostObjectRepository(db)
    success = await repo.soft_delete(object_id)
    if not success:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Cost Object {object_id} não encontrado"
        )
    await db.commit()
    logger.info(f"Cost Object removido: {object_id} por {current_user.id}")


@router.post("/objects/{object_id}/add-direct-cost", response_model=CostObjectResponse, status_code=201)
async def add_direct_cost(  # pylint: disable=unused-argument
    object_id: UUID,
    data: CostObjectAddDirectCost,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permissions(["costing.update"])),
) -> CostObjectResponse:
    """Adiciona custo direto a um objeto."""
    repo = CostObjectRepository(db)
    obj = await repo.add_direct_cost(object_id, data.valor, data.descricao)
    if not obj:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Cost Object {object_id} não encontrado"
        )
    await db.commit()

    logger.info(f"Custo direto adicionado ao objeto {object_id}: R$ {data.valor}")
    return CostObjectResponse.model_validate(obj)


@router.get("/objects/{object_id}/break-even")
async def get_break_even(  # pylint: disable=unused-argument
    object_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """Calcula ponto de equilíbrio do objeto."""
    service = ABCService(db)
    return await service.calculate_break_even(object_id)


@router.get("/objects/ranking/profitability")
async def get_profitability_ranking(
    condominio_id: UUID | None = None,
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[dict]:
    """Obtém ranking de lucratividade dos objetos."""
    repo = CostObjectRepository(db)
    return await repo.get_profitability_ranking(
        condominio_id=condominio_id or current_user.condominio_id,
        limit=limit,
    )


@router.get("/objects/unprofitable")
async def get_unprofitable_objects(
    condominio_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[CostObjectResponse]:
    """Lista objetos não lucrativos."""
    repo = CostObjectRepository(db)
    objects = await repo.get_unprofitable(condominio_id=condominio_id or current_user.condominio_id)
    return [CostObjectResponse.model_validate(o) for o in objects]


# ============================================================
# COST ALLOCATION ENDPOINTS
# ============================================================


@router.get("/allocations", response_model=list[CostAllocationResponse])
async def list_allocations(
    condominio_id: UUID | None = None,
    tipo: str | None = None,
    status: str | None = None,
    origem_id: UUID | None = None,
    destino_id: UUID | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[CostAllocationResponse]:
    """Lista alocações de custo com filtros."""
    repo = CostAllocationRepository(db)
    filters = CostAllocationFilter(
        condominio_id=condominio_id or current_user.condominio_id,
        tipo=tipo,
        status=status,
        origem_id=origem_id,
        destino_id=destino_id,
        data_inicio=data_inicio,
        data_fim=data_fim,
    )
    allocations = await repo.get_multi(filters=filters, skip=skip, limit=limit)
    return [CostAllocationResponse.model_validate(a) for a in allocations]


@router.post(
    "/allocations",
    response_model=CostAllocationResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_allocation(
    data: CostAllocationCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permissions(["costing.allocate"])),
) -> CostAllocationResponse:
    """Cria nova alocação de custo."""
    repo = CostAllocationRepository(db)

    if not data.condominio_id:
        data.condominio_id = current_user.condominio_id

    # pylint: disable=unexpected-keyword-arg
    allocation = await repo.create(data, user_id=current_user.id)
    await db.commit()

    logger.info(f"Cost Allocation criada: {allocation.id} por {current_user.id}")
    return CostAllocationResponse.model_validate(allocation)


@router.get("/allocations/{allocation_id}", response_model=CostAllocationResponse)
async def get_allocation(  # pylint: disable=unused-argument
    allocation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> CostAllocationResponse:
    """Obtém alocação por ID."""
    repo = CostAllocationRepository(db)
    allocation = await repo.get(allocation_id)
    if not allocation:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Cost Allocation {allocation_id} não encontrada"
        )
    return CostAllocationResponse.model_validate(allocation)


@router.post("/allocations/{allocation_id}/approve", response_model=CostAllocationResponse, status_code=201)
async def approve_allocation(
    allocation_id: UUID,
    data: CostAllocationApprove,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permissions(["costing.approve"])),
) -> CostAllocationResponse:
    """Aprova uma alocação pendente."""
    service = AllocationService(db)
    allocation = await service.approve_allocation(
        allocation_id,
        user_id=current_user.id,
        observacao=data.observacao,
    )
    await db.commit()

    logger.info(f"Alocação aprovada: {allocation_id} por {current_user.id}")
    return CostAllocationResponse.model_validate(allocation)


@router.post("/allocations/{allocation_id}/execute", response_model=CostAllocationResponse, status_code=201)
async def execute_allocation(
    allocation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permissions(["costing.execute"])),
) -> CostAllocationResponse:
    """Executa uma alocação aprovada."""
    service = AllocationService(db)
    allocation = await service.execute_allocation(allocation_id, user_id=current_user.id)
    await db.commit()

    logger.info(f"Alocação executada: {allocation_id} por {current_user.id}")
    return CostAllocationResponse.model_validate(allocation)


@router.post("/allocations/{allocation_id}/reverse", response_model=CostAllocationResponse, status_code=201)
async def reverse_allocation(
    allocation_id: UUID,
    data: CostAllocationReverse,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permissions(["costing.reverse"])),
) -> CostAllocationResponse:
    """Reverte uma alocação executada."""
    service = AllocationService(db)
    reversal = await service.reverse_allocation(
        allocation_id,
        user_id=current_user.id,
        motivo=data.motivo,
    )
    await db.commit()

    logger.info(f"Alocação revertida: {allocation_id} por {current_user.id}")
    return CostAllocationResponse.model_validate(reversal)


@router.post("/allocations/batch-execute", status_code=201)
async def batch_execute_allocations(
    data: CostAllocationBatch,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permissions(["costing.execute"])),
) -> dict:
    """Executa múltiplas alocações em lote."""
    service = AllocationService(db)
    result = await service.batch_execute(data.allocation_ids, user_id=current_user.id)

    logger.info(f"Lote executado: {result['executadas']}/{result['total_solicitadas']}")
    return result


@router.post("/allocations/pool-to-activities", status_code=201)
async def allocate_pool_to_activities(
    pool_id: UUID,
    allocations: list[dict],
    data_alocacao: date = Query(...),
    auto_execute: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permissions(["costing.allocate"])),
) -> list[CostAllocationResponse]:
    """Aloca custos de um pool para múltiplas atividades."""
    service = AllocationService(db)
    created = await service.allocate_pool_to_activities(
        pool_id=pool_id,
        activity_allocations=allocations,
        data_alocacao=data_alocacao,
        user_id=current_user.id,
        auto_execute=auto_execute,
    )
    await db.commit()

    return [CostAllocationResponse.model_validate(a) for a in created]


@router.post("/allocations/activity-to-objects", status_code=201)
async def allocate_activity_to_objects(
    activity_id: UUID,
    allocations: list[dict],
    data_alocacao: date = Query(...),
    auto_execute: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permissions(["costing.allocate"])),
) -> list[CostAllocationResponse]:
    """Aloca custos de uma atividade para múltiplos objetos."""
    service = AllocationService(db)
    created = await service.allocate_activity_to_objects(
        activity_id=activity_id,
        object_allocations=allocations,
        data_alocacao=data_alocacao,
        user_id=current_user.id,
        auto_execute=auto_execute,
    )
    await db.commit()

    return [CostAllocationResponse.model_validate(a) for a in created]


@router.post("/allocations/by-driver", status_code=201)
async def allocate_by_driver(
    origem_tipo: str,
    origem_id: UUID,
    driver_id: UUID,
    destinos: list[dict],
    data_alocacao: date = Query(...),
    auto_execute: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permissions(["costing.allocate"])),
) -> list[CostAllocationResponse]:
    """Aloca custos proporcionalmente ao consumo de um driver."""
    service = AllocationService(db)
    created = await service.allocate_by_driver(
        origem_tipo=origem_tipo,
        origem_id=origem_id,
        driver_id=driver_id,
        destinos=destinos,
        data_alocacao=data_alocacao,
        user_id=current_user.id,
        auto_execute=auto_execute,
    )
    await db.commit()

    return [CostAllocationResponse.model_validate(a) for a in created]


@router.get("/allocations/summary", response_model=AllocationSummary)
async def get_allocation_summary(
    condominio_id: UUID | None = None,
    periodo_inicio: date = Query(...),
    periodo_fim: date = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> AllocationSummary:
    """Obtém resumo das alocações do período."""
    service = AllocationService(db)
    summary = await service.get_allocation_summary(
        condominio_id=condominio_id or current_user.condominio_id,
        periodo_inicio=periodo_inicio,
        periodo_fim=periodo_fim,
    )
    return AllocationSummary(**summary)


# ============================================================
# COST ANALYSIS ENDPOINTS
# ============================================================


@router.get("/analyses", response_model=list[CostAnalysisResponse])
async def list_analyses(
    condominio_id: UUID | None = None,
    tipo: str | None = None,
    status: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[CostAnalysisResponse]:
    """Lista análises de custo."""
    repo = CostAnalysisRepository(db)
    filters = CostAnalysisFilter(
        condominio_id=condominio_id or current_user.condominio_id,
        tipo=tipo,
        status=status,
    )
    analyses = await repo.get_multi(filters=filters, skip=skip, limit=limit)
    return [CostAnalysisResponse.model_validate(a) for a in analyses]


@router.get("/analyses/{analysis_id}", response_model=CostAnalysisResponse)
async def get_analysis(  # pylint: disable=unused-argument
    analysis_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> CostAnalysisResponse:
    """Obtém análise por ID."""
    repo = CostAnalysisRepository(db)
    analysis = await repo.get(analysis_id)
    if not analysis:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Cost Analysis {analysis_id} não encontrada"
        )
    return CostAnalysisResponse.model_validate(analysis)


@router.post("/analyses/run-abc", response_model=dict, status_code=201)
async def run_abc_costing(
    data: CostAnalysisRun,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permissions(["costing.analyze"])),
) -> dict:
    """Executa custeio ABC completo para o período."""
    service = ABCService(db)
    result = await service.run_abc_costing(
        condominio_id=data.condominio_id or current_user.condominio_id,
        periodo_inicio=data.periodo_inicio,
        periodo_fim=data.periodo_fim,
        user_id=current_user.id,
    )
    await db.commit()

    logger.info(f"Custeio ABC executado por {current_user.id}")
    return result


@router.post("/analyses/run-ai", response_model=dict, status_code=201)
async def run_ai_analysis(
    data: CostAnalysisRun,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permissions(["costing.analyze"])),
) -> dict:
    """Executa análise de custos com IA."""
    condo_id = data.condominio_id or current_user.condominio_id
    code = f"AI-{dt.utcnow().strftime('%Y%m%d%H%M%S')}"

    # Cria objeto de análise
    analysis = CostAnalysis(
        condominio_id=condo_id,
        code=code,
        name=data.name or f"Análise {data.periodo_inicio} a {data.periodo_fim}",
        period_start=dt.combine(data.periodo_inicio, dt.min.time()),
        period_end=dt.combine(data.periodo_fim, dt.max.time()),
        created_by=current_user.id,
    )

    # Salva no repositório
    analysis_repo = CostAnalysisRepository(db)
    analysis = await analysis_repo.create(analysis)

    # Executa a análise
    service = CostAIService(db)
    result = await service.run_analysis(
        analysis=analysis,
        condominio_id=condo_id,
    )
    await db.commit()

    logger.info(f"Análise IA executada por {current_user.id}")
    return {"analysis_id": str(result.id), "status": result.status.value}


@router.get("/analyses/profitability")
async def analyze_profitability(
    condominio_id: UUID | None = None,
    object_ids: list[UUID] | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """Analisa lucratividade dos objetos de custo."""
    service = CostAIService(db)
    return await service.analyze_profitability(
        condominio_id=condominio_id or current_user.condominio_id,
        object_ids=object_ids,
    )


@router.get("/analyses/idle-capacity")
async def analyze_idle_capacity(
    condominio_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """Analisa capacidade ociosa dos drivers."""
    service = CostAIService(db)
    return await service.analyze_idle_capacity(condominio_id=condominio_id or current_user.condominio_id)


@router.get("/analyses/anomalies")
async def detect_anomalies(
    condominio_id: UUID | None = None,
    period: str | None = None,
    z_score_threshold: float = Query(2.0),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """Detecta anomalias nos custos."""
    service = CostAIService(db)
    return await service.detect_cost_anomalies(
        condominio_id=condominio_id or current_user.condominio_id,
        period=period,
        z_score_threshold=z_score_threshold,
    )


@router.get("/analyses/optimization-suggestions")
async def get_optimization_suggestions(
    condominio_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[dict]:
    """Obtém sugestões de otimização de custos."""
    service = CostAIService(db)
    return await service.suggest_cost_optimization(condominio_id=condominio_id or current_user.condominio_id)


@router.get("/analyses/forecast")
async def forecast_costs(
    condominio_id: UUID | None = None,
    periods_ahead: int = Query(3, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """Projeta custos futuros."""
    service = CostAIService(db)
    return await service.forecast_costs(
        condominio_id=condominio_id or current_user.condominio_id,
        periods_ahead=periods_ahead,
    )


# ============================================================
# DASHBOARD & STATISTICS ENDPOINTS
# ============================================================


@router.get("/dashboard", response_model=ABCDashboard)
async def get_dashboard(  # pylint: disable=too-many-locals,unused-argument
    condominio_id: UUID | None = None,
    periodo_inicio: date | None = None,
    periodo_fim: date | None = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> ABCDashboard:
    """Obtém dashboard de custeio ABC."""
    condo_id = condominio_id or current_user.condominio_id

    # Repositórios
    driver_repo = CostDriverRepository(db)
    activity_repo = CostActivityRepository(db)
    pool_repo = CostPoolRepository(db)
    object_repo = CostObjectRepository(db)
    allocation_repo = CostAllocationRepository(db)

    # Estatísticas
    driver_stats = await driver_repo.get_statistics(condo_id)
    activity_stats = await activity_repo.get_statistics(condo_id)
    pool_stats = await pool_repo.get_statistics(condo_id)
    object_stats = await object_repo.get_statistics(condo_id)
    allocation_stats = await allocation_repo.get_statistics(condo_id)

    return ABCDashboard(
        total_drivers=driver_stats.get("total", 0),
        total_activities=activity_stats.get("total", 0),
        total_pools=pool_stats.get("total", 0),
        total_objects=object_stats.get("total", 0),
        total_allocations=allocation_stats.get("total", 0),
        custo_total_pools=pool_stats.get("valor_total", 0),
        custo_total_alocado=allocation_stats.get("valor_executado", 0),
        capacidade_ociosa=driver_stats.get("capacidade_ociosa_total", 0),
        margem_media=object_stats.get("margem_media", 0),
        objetos_lucrativos=object_stats.get("lucrativos", 0),
        objetos_nao_lucrativos=object_stats.get("nao_lucrativos", 0),
    )


@router.get("/stats", response_model=CostingStats)
async def get_stats(
    condominio_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> CostingStats:
    """Obtém estatísticas gerais de custeio."""
    condo_id = condominio_id or current_user.condominio_id

    driver_repo = CostDriverRepository(db)
    activity_repo = CostActivityRepository(db)
    pool_repo = CostPoolRepository(db)
    object_repo = CostObjectRepository(db)
    allocation_repo = CostAllocationRepository(db)
    analysis_repo = CostAnalysisRepository(db)

    return CostingStats(
        drivers=await driver_repo.get_statistics(condo_id),
        activities=await activity_repo.get_statistics(condo_id),
        pools=await pool_repo.get_statistics(condo_id),
        objects=await object_repo.get_statistics(condo_id),
        allocations=await allocation_repo.get_statistics(condo_id),
        analyses=await analysis_repo.get_statistics(condo_id),
    )


@router.get("/trends", response_model=list[CostTrend])
async def get_cost_trends(
    condominio_id: UUID | None = None,
    meses: int = Query(12, ge=1, le=36),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[CostTrend]:
    """Obtém tendências de custos por mês."""
    allocation_repo = CostAllocationRepository(db)
    trends = await allocation_repo.get_monthly_trends(
        condominio_id=condominio_id or current_user.condominio_id,
        meses=meses,
    )
    return [CostTrend(**t) for t in trends]
