"""Controller para EquipmentMaintenance."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.equipment_management.schemas.maintenance import (
    MaintenanceCreate,
    MaintenanceFilter,
    MaintenanceListResponse,
    MaintenanceResponse,
    MaintenanceStats,
    MaintenanceUpdate,
)
from modules.equipment_management.services.maintenance_ai_service import (
    MaintenanceAIService,
)
from modules.equipment_management.services.maintenance_service import (
    MaintenanceService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/maintenances", tags=["Maintenances"])


async def get_service(db: AsyncSession = Depends(get_db)) -> MaintenanceService:
    """Dependency para obter o service."""
    return MaintenanceService(db)


async def get_ai_service(db: AsyncSession = Depends(get_db)) -> MaintenanceAIService:
    """Dependency para obter o AI service."""
    return MaintenanceAIService(db)


@router.post("", response_model=MaintenanceResponse, status_code=status.HTTP_201_CREATED)
async def create_maintenance(
    data: MaintenanceCreate,
    current_user: CurrentActiveUser,
    service: MaintenanceService = Depends(get_service),
) -> MaintenanceResponse:
    """Cria uma nova manutenção."""
    try:
        return await service.create(data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao criar manutenção: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar manutenção",
        )


@router.get("", response_model=MaintenanceListResponse)
@router.get("/", response_model=MaintenanceListResponse, include_in_schema=False)  # espelho barra-final
async def list_maintenances(  # pylint: disable=too-many-locals
    current_user: CurrentActiveUser,
    search: str | None = Query(None),
    maintenance_type: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    priority: str | None = Query(None),
    equipment_id: str | None = Query(None),
    client_id: str | None = Query(None),
    technician_id: str | None = Query(None),
    is_overdue: bool | None = Query(None),
    is_warranty: bool | None = Query(None),
    problem_resolved: bool | None = Query(None),
    needs_followup: bool | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: MaintenanceService = Depends(get_service),
) -> MaintenanceListResponse:
    """Lista manutenções com filtros."""
    filters = MaintenanceFilter(
        search=search,
        maintenance_type=maintenance_type,
        status=status_filter,
        priority=priority,
        equipment_id=equipment_id,
        client_id=client_id,
        technician_id=technician_id,
        is_overdue=is_overdue,
        is_warranty=is_warranty,
        problem_resolved=problem_resolved,
        needs_followup=needs_followup,
        date_from=date_from,
        date_to=date_to,
    )
    return await service.list_with_filters(filters, page, page_size)


@router.get("/stats", response_model=MaintenanceStats)
async def get_stats(
    current_user: CurrentActiveUser,
    client_id: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    service: MaintenanceService = Depends(get_service),
) -> MaintenanceStats:
    """Obtém estatísticas de manutenções."""
    return await service.get_stats(client_id, date_from, date_to)


@router.get("/overdue", response_model=list[MaintenanceResponse])
async def get_overdue(
    current_user: CurrentActiveUser,
    service: MaintenanceService = Depends(get_service),
) -> list[MaintenanceResponse]:
    """Lista manutenções atrasadas."""
    return await service.get_overdue()


@router.get("/waiting-parts", response_model=list[MaintenanceResponse])
async def get_waiting_parts(
    current_user: CurrentActiveUser,
    service: MaintenanceService = Depends(get_service),
) -> list[MaintenanceResponse]:
    """Lista manutenções aguardando peças."""
    return await service.get_waiting_parts()


@router.get("/needing-followup", response_model=list[MaintenanceResponse])
async def get_needing_followup(
    current_user: CurrentActiveUser,
    service: MaintenanceService = Depends(get_service),
) -> list[MaintenanceResponse]:
    """Lista manutenções que precisam de follow-up."""
    return await service.get_needing_followup()


@router.get("/by-date/{date}", response_model=list[MaintenanceResponse])
async def get_by_date(
    date: datetime,
    current_user: CurrentActiveUser,
    service: MaintenanceService = Depends(get_service),
) -> list[MaintenanceResponse]:
    """Lista manutenções agendadas para uma data."""
    return await service.get_scheduled_for_date(date)


@router.get("/by-equipment/{equipment_id}", response_model=list[MaintenanceResponse])
async def get_by_equipment(
    equipment_id: str,
    current_user: CurrentActiveUser,
    service: MaintenanceService = Depends(get_service),
) -> list[MaintenanceResponse]:
    """Lista manutenções de um equipamento."""
    return await service.get_by_equipment(equipment_id)


@router.get("/by-client/{client_id}", response_model=list[MaintenanceResponse])
async def get_by_client(
    client_id: str,
    current_user: CurrentActiveUser,
    service: MaintenanceService = Depends(get_service),
) -> list[MaintenanceResponse]:
    """Lista manutenções de um cliente."""
    return await service.get_by_client(client_id)


@router.get("/by-technician/{technician_id}", response_model=list[MaintenanceResponse])
async def get_by_technician(
    technician_id: str,
    current_user: CurrentActiveUser,
    include_completed: bool = Query(False),
    service: MaintenanceService = Depends(get_service),
) -> list[MaintenanceResponse]:
    """Lista manutenções de um técnico."""
    return await service.get_by_technician(technician_id, include_completed)


# AI Endpoints
@router.get("/ai/health/{equipment_id}")
async def analyze_health(
    equipment_id: str,
    current_user: CurrentActiveUser,
    ai_service: MaintenanceAIService = Depends(get_ai_service),
) -> dict:
    """Analisa saúde do equipamento usando IA."""
    result = await ai_service.analyze_equipment_health(equipment_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Equipamento não encontrado",
        )
    return result


@router.get("/ai/predict-failure/{equipment_id}")
async def predict_failure(
    equipment_id: str,
    current_user: CurrentActiveUser,
    ai_service: MaintenanceAIService = Depends(get_ai_service),
) -> dict:
    """Prevê probabilidade de falha do equipamento."""
    result = await ai_service.predict_failure(equipment_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Equipamento não encontrado",
        )
    return result


@router.get("/ai/recommend-schedule")
async def recommend_schedule(
    current_user: CurrentActiveUser,
    client_id: str | None = Query(None),
    ai_service: MaintenanceAIService = Depends(get_ai_service),
) -> list[dict]:
    """Recomenda agenda de manutenções preventivas."""
    return await ai_service.recommend_maintenance_schedule(client_id)


@router.get("/ai/optimize-route/{technician_id}")
async def optimize_route(
    technician_id: str,
    date: datetime,
    current_user: CurrentActiveUser,
    ai_service: MaintenanceAIService = Depends(get_ai_service),
) -> list[dict]:
    """Otimiza rota de manutenções para técnico."""
    return await ai_service.optimize_technician_route(technician_id, date)


@router.get("/ai/patterns")
async def analyze_patterns(
    current_user: CurrentActiveUser,
    client_id: str | None = Query(None),
    months: int = Query(12, ge=1, le=24),
    ai_service: MaintenanceAIService = Depends(get_ai_service),
) -> dict:
    """Analisa padrões de manutenção."""
    return await ai_service.analyze_maintenance_patterns(client_id, months)


@router.get("/ai/estimate-cost/{equipment_id}")
async def estimate_cost(
    equipment_id: str,
    current_user: CurrentActiveUser,
    maintenance_type: str = Query("preventiva"),
    ai_service: MaintenanceAIService = Depends(get_ai_service),
) -> dict:
    """Estima custo de manutenção."""
    result = await ai_service.estimate_maintenance_cost(equipment_id, maintenance_type)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Equipamento não encontrado",
        )
    return result


@router.get("/code/{code}", response_model=MaintenanceResponse)
async def get_by_code(
    code: str,
    current_user: CurrentActiveUser,
    service: MaintenanceService = Depends(get_service),
) -> MaintenanceResponse:
    """Busca manutenção por código."""
    maintenance = await service.get_by_code(code)
    if not maintenance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manutenção não encontrada",
        )
    return maintenance


@router.get("/{maintenance_id}", response_model=MaintenanceResponse)
async def get_maintenance(
    maintenance_id: str,
    current_user: CurrentActiveUser,
    service: MaintenanceService = Depends(get_service),
) -> MaintenanceResponse:
    """Busca manutenção por ID."""
    maintenance = await service.get_by_id(maintenance_id)
    if not maintenance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manutenção não encontrada",
        )
    return maintenance


@router.put("/{maintenance_id}", response_model=MaintenanceResponse)
async def update_maintenance(
    maintenance_id: str,
    data: MaintenanceUpdate,
    current_user: CurrentActiveUser,
    service: MaintenanceService = Depends(get_service),
) -> MaintenanceResponse:
    """Atualiza uma manutenção."""
    maintenance = await service.update(maintenance_id, data)
    if not maintenance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manutenção não encontrada",
        )
    return maintenance


@router.delete("/{maintenance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_maintenance(
    maintenance_id: str,
    current_user: CurrentActiveUser,
    service: MaintenanceService = Depends(get_service),
) -> None:
    """Remove uma manutenção (soft delete)."""
    result = await service.delete(maintenance_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manutenção não encontrada",
        )


@router.post("/{maintenance_id}/start", response_model=MaintenanceResponse, status_code=201)
async def start_maintenance(
    maintenance_id: str,
    current_user: CurrentActiveUser,
    service: MaintenanceService = Depends(get_service),
) -> MaintenanceResponse:
    """Inicia uma manutenção."""
    maintenance = await service.start(maintenance_id)
    if not maintenance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manutenção não encontrada",
        )
    return maintenance


@router.post("/{maintenance_id}/complete", response_model=MaintenanceResponse, status_code=201)
async def complete_maintenance(
    maintenance_id: str,
    current_user: CurrentActiveUser,
    problem_resolved: bool = True,
    equipment_status_after: str | None = None,
    service: MaintenanceService = Depends(get_service),
) -> MaintenanceResponse:
    """Conclui uma manutenção."""
    maintenance = await service.complete(maintenance_id, problem_resolved, equipment_status_after)
    if not maintenance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manutenção não encontrada",
        )
    return maintenance


@router.post("/{maintenance_id}/cancel", response_model=MaintenanceResponse, status_code=201)
async def cancel_maintenance(
    maintenance_id: str,
    current_user: CurrentActiveUser,
    service: MaintenanceService = Depends(get_service),
) -> MaintenanceResponse:
    """Cancela uma manutenção."""
    maintenance = await service.cancel(maintenance_id)
    if not maintenance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manutenção não encontrada",
        )
    return maintenance


@router.post("/{maintenance_id}/waiting-parts", response_model=MaintenanceResponse, status_code=201)
async def mark_waiting_parts(
    maintenance_id: str,
    parts_requested: list,
    current_user: CurrentActiveUser,
    service: MaintenanceService = Depends(get_service),
) -> MaintenanceResponse:
    """Marca como aguardando peças."""
    maintenance = await service.mark_waiting_parts(maintenance_id, parts_requested)
    if not maintenance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manutenção não encontrada",
        )
    return maintenance


@router.post("/{maintenance_id}/add-part", response_model=MaintenanceResponse, status_code=201)
async def add_part_replaced(
    maintenance_id: str,
    part_name: str,
    current_user: CurrentActiveUser,
    part_code: str | None = None,
    quantity: int = 1,
    unit_cost: float = 0.0,
    service: MaintenanceService = Depends(get_service),
) -> MaintenanceResponse:
    """Adiciona peça substituída."""
    maintenance = await service.add_part_replaced(maintenance_id, part_name, part_code, quantity, unit_cost)
    if not maintenance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manutenção não encontrada",
        )
    return maintenance


@router.post("/{maintenance_id}/sign", response_model=MaintenanceResponse, status_code=201)
async def sign_maintenance(
    maintenance_id: str,
    signed_by: str,
    signature: str,
    current_user: CurrentActiveUser,
    service: MaintenanceService = Depends(get_service),
) -> MaintenanceResponse:
    """Registra assinatura do cliente."""
    maintenance = await service.sign_by_client(maintenance_id, signed_by, signature)
    if not maintenance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manutenção não encontrada",
        )
    return maintenance


@router.post("/{maintenance_id}/assign-technician", response_model=MaintenanceResponse, status_code=201)
async def assign_technician(
    maintenance_id: str,
    technician_id: str,
    technician_name: str,
    current_user: CurrentActiveUser,
    service: MaintenanceService = Depends(get_service),
) -> MaintenanceResponse:
    """Atribui técnico à manutenção."""
    maintenance = await service.assign_technician(maintenance_id, technician_id, technician_name)
    if not maintenance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manutenção não encontrada",
        )
    return maintenance


@router.post("/schedule-preventive/{equipment_id}", response_model=MaintenanceResponse, status_code=201)
async def schedule_preventive(
    equipment_id: str,
    current_user: CurrentActiveUser,
    interval_days: int = Query(90, ge=1),
    checklist_template_id: str | None = None,
    service: MaintenanceService = Depends(get_service),
) -> MaintenanceResponse:
    """Agenda manutenção preventiva para equipamento."""
    maintenance = await service.schedule_preventive(equipment_id, interval_days, checklist_template_id)
    if not maintenance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Equipamento não encontrado",
        )
    return maintenance
