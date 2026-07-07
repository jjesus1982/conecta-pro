"""
Controller de Rondas de Inspecao - Endpoints FastAPI.

Author: Conecta PRO Team
Date: 2026-01-23
"""

import asyncio
import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser, get_current_active_user
from core.database import get_db
from modules.operacional.publishers import publish_ronda_concluida

from ..schemas import (
    ApplyDisciplinaryRequest,
    CheckpointCreate,
    CheckpointResponse,
    CheckpointUpdate,
    CompleteRoundRequest,
    InspectionDashboardStats,
    InspectionRoundCreate,
    InspectionRoundFilter,
    InspectionRoundListResponse,
    InspectionRoundResponse,
    InspectionRoundSummary,
    InspectionRoundUpdate,
    RegisterOccurrenceRequest,
    StartRoundRequest,
)
from ..services import (
    InspectionRoundNotFoundError,
    InspectionRoundService,
    InspectionRoundValidationError,
)

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_active_user)])


def get_inspection_service(db: AsyncSession = Depends(get_db)) -> InspectionRoundService:
    """Dependency para obter InspectionRoundService."""
    return InspectionRoundService(db)


# =============================================================================
# CRUD ENDPOINTS
# =============================================================================


@router.post(
    "/",
    response_model=InspectionRoundResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar ronda de inspecao",
    description="Cria uma nova ronda de inspecao.",
)
async def create_round(
    data: InspectionRoundCreate,
    current_user: CurrentActiveUser,
    service: InspectionRoundService = Depends(get_inspection_service),
) -> InspectionRoundResponse:
    """Cria uma nova ronda."""
    try:
        inspection_round = await service.create(data)
        return InspectionRoundResponse.model_validate(inspection_round)
    except InspectionRoundValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Erro ao criar ronda: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao criar ronda",
        )


@router.get(
    "/",
    response_model=InspectionRoundListResponse,
    summary="Listar rondas",
    description="Lista rondas com filtros e paginacao.",
)
async def list_rounds(  # pylint: disable=too-many-locals
    current_user: CurrentActiveUser,
    tenant_id: UUID | None = Query(None, description="ID do tenant (opcional)"),
    page: int = Query(1, ge=1, description="Página atual"),
    page_size: int = Query(10, ge=1, le=100, description="Itens por página"),
    skip: int = Query(0, ge=0, description="Registros a pular"),
    limit: int = Query(100, ge=1, le=500, description="Limite de registros"),
    inspector_id: UUID | None = Query(None, description="Filtrar por inspetor"),
    inspector_role: str | None = Query(None, description="Filtrar por cargo"),
    status_filter: str | None = Query(None, alias="status", description="Filtrar por status"),
    start_date: datetime | None = Query(None, description="Data inicial"),
    end_date: datetime | None = Query(None, description="Data final"),
    has_occurrences: bool | None = Query(None, description="Com ocorrencias"),
    has_disciplinary_actions: bool | None = Query(None, description="Com medidas disciplinares"),
    service: InspectionRoundService = Depends(get_inspection_service),
) -> InspectionRoundListResponse:
    """Lista rondas com filtros."""
    filters = InspectionRoundFilter(
        inspector_id=inspector_id,
        inspector_role=inspector_role,
        status=status_filter,
        start_date=start_date,
        end_date=end_date,
        has_occurrences=has_occurrences,
        has_disciplinary_actions=has_disciplinary_actions,
    )

    # Calcular skip a partir de page/page_size se fornecidos
    actual_skip = (page - 1) * page_size if page > 0 else skip
    actual_limit = page_size if page_size > 0 else limit

    tenant_str = str(tenant_id) if tenant_id else None
    rounds, total = await service.list(tenant_str, actual_skip, actual_limit, filters)

    total_pages = (total + actual_limit - 1) // actual_limit if actual_limit > 0 else 0

    return InspectionRoundListResponse(
        items=[InspectionRoundSummary.model_validate(r) for r in rounds],
        total=total,
        page=page,
        page_size=actual_limit,
        pages=total_pages,
    )


@router.get(
    "/stats",
    response_model=InspectionDashboardStats,
    summary="Estatísticas de rondas",
    description="Retorna estatísticas de rondas de inspeção.",
)
async def get_stats(
    current_user: CurrentActiveUser,
    tenant_id: UUID | None = Query(None, description="ID do tenant (opcional)"),
    service: InspectionRoundService = Depends(get_inspection_service),
) -> InspectionDashboardStats:
    """Retorna estatísticas de rondas."""
    tenant_str = str(tenant_id) if tenant_id else None
    return await service.get_dashboard_stats(tenant_str)


@router.get(
    "/dashboard",
    response_model=InspectionDashboardStats,
    summary="Dashboard de rondas",
    description="Retorna estatisticas do dashboard de rondas.",
)
async def get_dashboard(
    current_user: CurrentActiveUser,
    tenant_id: UUID | None = Query(None, description="ID do tenant (opcional)"),
    _start_date: datetime | None = Query(None, description="Data inicial"),
    _end_date: datetime | None = Query(None, description="Data final"),
    service: InspectionRoundService = Depends(get_inspection_service),
) -> InspectionDashboardStats:
    """Retorna estatisticas do dashboard."""
    tenant_str = str(tenant_id) if tenant_id else None
    return await service.get_dashboard_stats(tenant_str)


@router.get(
    "/minhas-rondas",
    response_model=list[InspectionRoundSummary],
    summary="Minhas rondas",
    description="Lista rondas do inspetor logado.",
)
async def get_my_rounds(
    current_user: CurrentActiveUser,
    inspector_id: UUID = Query(..., description="ID do inspetor"),
    tenant_id: UUID = Query(..., description="ID do tenant"),
    limit: int = Query(50, ge=1, le=200),
    service: InspectionRoundService = Depends(get_inspection_service),
) -> list[InspectionRoundSummary]:
    """Lista rondas do inspetor."""
    rounds = await service.get_rounds_by_inspector(str(inspector_id), str(tenant_id), limit)
    return [InspectionRoundSummary.model_validate(r) for r in rounds]


@router.get(
    "/{round_id}",
    response_model=InspectionRoundResponse,
    summary="Buscar ronda",
    description="Busca uma ronda por ID.",
)
async def get_round(
    round_id: UUID,
    current_user: CurrentActiveUser,
    service: InspectionRoundService = Depends(get_inspection_service),
) -> InspectionRoundResponse:
    """Busca ronda por ID."""
    try:
        inspection_round = await service.get_by_id(str(round_id))
        return InspectionRoundResponse.model_validate(inspection_round)
    except InspectionRoundNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.patch(
    "/{round_id}",
    response_model=InspectionRoundResponse,
    summary="Atualizar ronda",
    description="Atualiza uma ronda existente.",
)
async def update_round(
    round_id: UUID,
    data: InspectionRoundUpdate,
    current_user: CurrentActiveUser,
    service: InspectionRoundService = Depends(get_inspection_service),
) -> InspectionRoundResponse:
    """Atualiza uma ronda."""
    try:
        inspection_round = await service.update(str(round_id), data)
        return InspectionRoundResponse.model_validate(inspection_round)
    except InspectionRoundNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InspectionRoundValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete(
    "/{round_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remover ronda",
    description="Remove uma ronda (soft delete).",
)
async def delete_round(
    round_id: UUID,
    current_user: CurrentActiveUser,
    service: InspectionRoundService = Depends(get_inspection_service),
):
    """Remove uma ronda."""
    try:
        await service.delete(str(round_id))
    except InspectionRoundNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InspectionRoundValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# =============================================================================
# WORKFLOW ENDPOINTS
# =============================================================================


@router.post(
    "/{round_id}/iniciar",
    response_model=InspectionRoundResponse,
    summary="Iniciar ronda",
    description="Inicia uma ronda agendada.",
    status_code=201,
)
async def start_round(
    round_id: UUID,
    current_user: CurrentActiveUser,
    data: StartRoundRequest | None = None,
    service: InspectionRoundService = Depends(get_inspection_service),
) -> InspectionRoundResponse:
    """Inicia uma ronda."""
    try:
        inspection_round = await service.start_round(str(round_id), data)
        return InspectionRoundResponse.model_validate(inspection_round)
    except InspectionRoundNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InspectionRoundValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/{round_id}/pausar",
    response_model=InspectionRoundResponse,
    summary="Pausar ronda",
    description="Pausa uma ronda em andamento.",
    status_code=201,
)
async def pause_round(
    round_id: UUID,
    current_user: CurrentActiveUser,
    service: InspectionRoundService = Depends(get_inspection_service),
) -> InspectionRoundResponse:
    """Pausa uma ronda."""
    try:
        inspection_round = await service.pause_round(str(round_id))
        return InspectionRoundResponse.model_validate(inspection_round)
    except InspectionRoundNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InspectionRoundValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/{round_id}/retomar",
    response_model=InspectionRoundResponse,
    summary="Retomar ronda",
    description="Retoma uma ronda pausada.",
    status_code=201,
)
async def resume_round(
    round_id: UUID,
    current_user: CurrentActiveUser,
    service: InspectionRoundService = Depends(get_inspection_service),
) -> InspectionRoundResponse:
    """Retoma uma ronda pausada."""
    try:
        inspection_round = await service.resume_round(str(round_id))
        return InspectionRoundResponse.model_validate(inspection_round)
    except InspectionRoundNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InspectionRoundValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/{round_id}/concluir",
    response_model=InspectionRoundResponse,
    summary="Concluir ronda",
    description="Conclui uma ronda em andamento.",
    status_code=201,
)
async def complete_round(
    round_id: UUID,
    current_user: CurrentActiveUser,
    data: CompleteRoundRequest | None = None,
    service: InspectionRoundService = Depends(get_inspection_service),
) -> InspectionRoundResponse:
    """Conclui uma ronda."""
    try:
        inspection_round = await service.complete_round(str(round_id), data)
        asyncio.create_task(
            publish_ronda_concluida(
                ronda_id=str(round_id),
                inspector_id=str(getattr(inspection_round, "inspector_id", "") or getattr(current_user, "id", "")),
                cliente_id=str(getattr(inspection_round, "tenant_id", "") or ""),
                total_checkpoints=len(getattr(inspection_round, "checkpoints", []) or []),
                tem_ocorrencias=bool(getattr(inspection_round, "has_occurrences", False)),
                data=datetime.utcnow().isoformat(),
            )
        )
        return InspectionRoundResponse.model_validate(inspection_round)
    except InspectionRoundNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InspectionRoundValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/{round_id}/cancelar",
    response_model=InspectionRoundResponse,
    summary="Cancelar ronda",
    description="Cancela uma ronda.",
    status_code=201,
)
async def cancel_round(
    round_id: UUID,
    current_user: CurrentActiveUser,
    reason: str | None = Query(None, description="Motivo do cancelamento"),
    service: InspectionRoundService = Depends(get_inspection_service),
) -> InspectionRoundResponse:
    """Cancela uma ronda."""
    try:
        inspection_round = await service.cancel_round(str(round_id), reason)
        return InspectionRoundResponse.model_validate(inspection_round)
    except InspectionRoundNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InspectionRoundValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# =============================================================================
# CHECKPOINT ENDPOINTS
# =============================================================================


@router.post(
    "/{round_id}/checkpoints",
    response_model=CheckpointResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar checkpoint",
    description="Cria um checkpoint durante a ronda.",
)
async def create_checkpoint(
    round_id: UUID,
    data: CheckpointCreate,
    current_user: CurrentActiveUser,
    service: InspectionRoundService = Depends(get_inspection_service),
) -> CheckpointResponse:
    """Cria um checkpoint."""
    try:
        checkpoint = await service.create_checkpoint(str(round_id), data)
        return CheckpointResponse.model_validate(checkpoint)
    except InspectionRoundNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InspectionRoundValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/{round_id}/checkpoints",
    response_model=list[CheckpointResponse],
    summary="Listar checkpoints",
    description="Lista checkpoints de uma ronda.",
)
async def get_checkpoints(
    round_id: UUID,
    current_user: CurrentActiveUser,
    service: InspectionRoundService = Depends(get_inspection_service),
) -> list[CheckpointResponse]:
    """Lista checkpoints de uma ronda."""
    try:
        checkpoints = await service.get_checkpoints(str(round_id))
        return [CheckpointResponse.model_validate(c) for c in checkpoints]
    except InspectionRoundNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.patch(
    "/{round_id}/checkpoints/{checkpoint_id}",
    response_model=CheckpointResponse,
    summary="Atualizar checkpoint",
    description="Atualiza um checkpoint.",
)
async def update_checkpoint(
    _round_id: UUID,
    checkpoint_id: UUID,
    data: CheckpointUpdate,
    current_user: CurrentActiveUser,
    service: InspectionRoundService = Depends(get_inspection_service),
) -> CheckpointResponse:
    """Atualiza um checkpoint."""
    try:
        checkpoint = service.update_checkpoint(str(checkpoint_id), data)
        return CheckpointResponse.model_validate(checkpoint)
    except InspectionRoundNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


# =============================================================================
# OCORRENCIA E MEDIDA DISCIPLINAR ENDPOINTS
# =============================================================================


@router.post(
    "/{round_id}/registrar-ocorrencia",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar ocorrencia",
    description="Registra uma ocorrencia durante a ronda.",
)
async def register_occurrence(
    round_id: UUID,
    data: RegisterOccurrenceRequest,
    current_user: CurrentActiveUser,
    service: InspectionRoundService = Depends(get_inspection_service),
) -> dict:
    """Registra uma ocorrencia durante a ronda."""
    try:
        checkpoint, occurrence_info = service.register_occurrence(str(round_id), data)
        return {
            "checkpoint": CheckpointResponse.model_validate(checkpoint),
            "occurrence": occurrence_info,
            "message": f"Ocorrencia {occurrence_info['occurrence_code']} registrada com sucesso",
        }
    except InspectionRoundNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InspectionRoundValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Erro ao registrar ocorrencia: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao registrar ocorrencia",
        )


@router.post(
    "/{round_id}/aplicar-medida-disciplinar",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Aplicar medida disciplinar",
    description="Aplica medida disciplinar durante a ronda.",
)
async def apply_disciplinary_action(
    round_id: UUID,
    data: ApplyDisciplinaryRequest,
    current_user: CurrentActiveUser,
    service: InspectionRoundService = Depends(get_inspection_service),
) -> dict:
    """Aplica medida disciplinar durante a ronda."""
    try:
        checkpoint, action_info = service.apply_disciplinary_action(str(round_id), data)
        return {
            "checkpoint": CheckpointResponse.model_validate(checkpoint),
            "disciplinary_action": action_info,
            "message": (f"Medida disciplinar {action_info['disciplinary_action_code']} aplicada com sucesso"),
        }
    except InspectionRoundNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InspectionRoundValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Erro ao aplicar medida disciplinar: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao aplicar medida disciplinar",
        )
