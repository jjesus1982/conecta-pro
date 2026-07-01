"""
Controller (endpoints) para Substitution (Substituição de Funcionário).
"""

import asyncio
from datetime import date
from uuid import UUID  # [Operacoes] tipar path id -> 500 (uuid cast) vira 422

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from core.logging import logger
from modules.operacional.models.substitution import SubstitutionReason, SubstitutionStatus
from modules.operacional.permissions import Permission, require_operacional_permission
from modules.operacional.publishers import publish_substituicao_realizada
from modules.operacional.repositories.substitution_repository import SubstitutionRepository
from modules.operacional.schemas.substitution import (
    SubstituteSuggestion,
    SubstitutionConfirm,
    SubstitutionCreate,
    SubstitutionFilter,
    SubstitutionListResponse,
    SubstitutionReject,
    SubstitutionResponse,
    SubstitutionSuggestRequest,
    SubstitutionUpdate,
)

router = APIRouter(prefix="/substitutions", tags=["Operations - Substitutions"])


@router.post(
    "/",
    response_model=SubstitutionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_operacional_permission(Permission.SUBSTITUTIONS_CREATE)],
)
async def create_substitution(
    data: SubstitutionCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> SubstitutionResponse:
    """
    Cria uma nova solicitação de substituição.

    Pode ser criada sem substituto definido (será sugerido pela IA).
    """
    repo = SubstitutionRepository(db)
    substitution = await repo.create(data, requested_by=current_user.id)

    logger.info(
        "Substituição criada com sucesso",
        action="create_substitution",
        substitution_id=str(substitution.id),
        original_employee_id=str(data.original_employee_id),
        substitution_date=str(data.substitution_date),
        user_id=str(current_user.id),
        user_email=current_user.email,
    )
    return SubstitutionResponse.model_validate(substitution)


@router.get(
    "/",
    response_model=SubstitutionListResponse,
    dependencies=[require_operacional_permission(Permission.SUBSTITUTIONS_CREATE, Permission.SUBSTITUTIONS_APPROVE)],
)
async def list_substitutions(  # pylint: disable=too-many-locals
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Página atual"),
    page_size: int = Query(20, ge=1, le=100, description="Itens por página"),
    shift_id: str | None = None,
    post_id: str | None = None,
    original_employee_id: str | None = None,
    substitute_employee_id: str | None = None,
    status_filter: SubstitutionStatus | None = Query(None, alias="status"),
    reason: SubstitutionReason | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    is_pending: bool | None = None,
    has_substitute: bool | None = None,
) -> SubstitutionListResponse:
    """
    Lista substituições com filtros e paginação.
    """
    repo = SubstitutionRepository(db)

    filters = SubstitutionFilter(
        shift_id=shift_id,
        post_id=post_id,
        original_employee_id=original_employee_id,
        substitute_employee_id=substitute_employee_id,
        status=status_filter,
        reason=reason,
        start_date=start_date,
        end_date=end_date,
        is_pending=is_pending,
        has_substitute=has_substitute,
    )

    substitutions, total = await repo.list(filters=filters, page=page, page_size=page_size)
    total_pages = (total + page_size - 1) // page_size

    return SubstitutionListResponse(
        items=[SubstitutionResponse.model_validate(s) for s in substitutions],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/pending",
    response_model=list[SubstitutionResponse],
    dependencies=[require_operacional_permission(Permission.SUBSTITUTIONS_APPROVE)],
)
async def get_pending_substitutions(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    post_id: str | None = None,
) -> list[SubstitutionResponse]:
    """
    Lista substituições pendentes (aguardando confirmação).
    """
    repo = SubstitutionRepository(db)

    filters = SubstitutionFilter(
        post_id=post_id,
        status=SubstitutionStatus.PENDING,
    )

    substitutions, _ = await repo.list(filters=filters, page=1, page_size=100)

    return [SubstitutionResponse.model_validate(s) for s in substitutions]


@router.post(
    "/suggest",
    response_model=list[SubstituteSuggestion],
    dependencies=[require_operacional_permission(Permission.SUBSTITUTIONS_CREATE)],
)
async def suggest_substitutes(
    data: SubstitutionSuggestRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),  # pylint: disable=unused-argument
) -> list[SubstituteSuggestion]:
    """
    Sugere substitutos usando IA.

    Analisa disponibilidade, qualificações, distância e histórico
    para recomendar os melhores candidatos.
    """
    # PENDENTE: Buscar dados do turno e funcionários disponíveis do banco
    # Por enquanto, retorna lista vazia com log

    logger.info(
        "Solicitação de sugestões de substitutos",
        action="suggest_substitutes",
        shift_id=str(data.shift_id),
        user_id=str(current_user.id),
        user_email=current_user.email,
    )

    # Exemplo de como usar o serviço (quando tiver os dados):
    # shift = await shift_repo.get_by_id(data.shift_id)
    # available = await allocation_repo.get_available_employees(...)
    # suggestions = substitution_service.suggest_substitutes(shift, available, data)

    return []


@router.get(
    "/by-date/{target_date}",
    response_model=list[SubstitutionResponse],
    dependencies=[require_operacional_permission(Permission.SUBSTITUTIONS_CREATE, Permission.SUBSTITUTIONS_APPROVE)],
)
async def get_substitutions_by_date(
    target_date: date,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    post_id: str | None = None,
) -> list[SubstitutionResponse]:
    """
    Lista substituições de uma data específica.
    """
    repo = SubstitutionRepository(db)

    filters = SubstitutionFilter(
        post_id=post_id,
        start_date=target_date,
        end_date=target_date,
    )

    substitutions, _ = await repo.list(filters=filters, page=1, page_size=100)

    return [SubstitutionResponse.model_validate(s) for s in substitutions]


@router.get(
    "/{substitution_id}",
    response_model=SubstitutionResponse,
    dependencies=[require_operacional_permission(Permission.SUBSTITUTIONS_CREATE, Permission.SUBSTITUTIONS_APPROVE)],
)
async def get_substitution(
    substitution_id: UUID,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> SubstitutionResponse:
    """
    Busca substituição por ID.
    """
    repo = SubstitutionRepository(db)
    substitution = await repo.get_by_id(substitution_id)

    if not substitution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Substituição não encontrada",
        )

    return SubstitutionResponse.model_validate(substitution)


@router.patch(
    "/{substitution_id}",
    response_model=SubstitutionResponse,
    dependencies=[require_operacional_permission(Permission.SUBSTITUTIONS_CREATE)],
)
async def update_substitution(
    substitution_id: str,
    data: SubstitutionUpdate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> SubstitutionResponse:
    """
    Atualiza uma substituição.
    """
    repo = SubstitutionRepository(db)
    substitution = await repo.update(substitution_id, data)

    if not substitution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Substituição não encontrada",
        )

    logger.info(
        "Substituição atualizada com sucesso",
        action="update_substitution",
        substitution_id=str(substitution.id),
        user_id=str(current_user.id),
        user_email=current_user.email,
    )
    return SubstitutionResponse.model_validate(substitution)


@router.post(
    "/{substitution_id}/confirm",
    response_model=SubstitutionResponse,
    dependencies=[require_operacional_permission(Permission.SUBSTITUTIONS_APPROVE)],
)
async def confirm_substitution(
    substitution_id: str,
    data: SubstitutionConfirm,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> SubstitutionResponse:
    """
    Confirma uma substituição atribuindo o substituto.
    """
    repo = SubstitutionRepository(db)
    substitution = await repo.confirm(
        substitution_id,
        data.substitute_employee_id,
        current_user.id,
        data.notes,
    )

    if not substitution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Substituição não encontrada ou já confirmada",
        )

    logger.info(
        f"Substituição confirmada por {current_user.email}: "
        f"{substitution.id} -> substituto {data.substitute_employee_id}"
    )
    asyncio.create_task(
        publish_substituicao_realizada(
            employee_original_id=str(substitution.employee_id) if hasattr(substitution, "employee_id") else None,
            substituto_id=str(data.substitute_employee_id),
            substituto_nome="",
            cliente_id=str(substitution.client_id)
            if hasattr(substitution, "client_id") and substitution.client_id
            else None,
            data=str(substitution.substitution_date) if hasattr(substitution, "substitution_date") else None,
            turno=str(substitution.shift_id) if hasattr(substitution, "shift_id") and substitution.shift_id else None,
        )
    )
    return SubstitutionResponse.model_validate(substitution)


@router.post(
    "/{substitution_id}/reject",
    response_model=SubstitutionResponse,
    dependencies=[require_operacional_permission(Permission.SUBSTITUTIONS_APPROVE)],
)
async def reject_substitution(
    substitution_id: str,
    data: SubstitutionReject,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> SubstitutionResponse:
    """
    Rejeita uma substituição.
    """
    repo = SubstitutionRepository(db)
    substitution = await repo.reject(substitution_id, data.rejection_reason)

    if not substitution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Substituição não encontrada ou já processada",
        )

    logger.info(
        "Substituição rejeitada",
        action="reject_substitution",
        substitution_id=str(substitution.id),
        user_id=str(current_user.id),
        user_email=current_user.email,
    )
    return SubstitutionResponse.model_validate(substitution)


@router.post(
    "/{substitution_id}/complete",
    response_model=SubstitutionResponse,
    dependencies=[require_operacional_permission(Permission.SUBSTITUTIONS_APPROVE)],
)
async def complete_substitution(
    substitution_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    overtime_hours: float = Query(0, ge=0, description="Horas extras realizadas"),
    additional_cost: float = Query(0, ge=0, description="Custo adicional"),
) -> SubstitutionResponse:
    """
    Marca substituição como concluída.
    """
    repo = SubstitutionRepository(db)
    substitution = await repo.complete(
        substitution_id,
        overtime_hours,
        additional_cost,
    )

    if not substitution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Substituição não encontrada ou não confirmada",
        )

    logger.info(
        "Substituição concluída com sucesso",
        action="complete_substitution",
        substitution_id=str(substitution.id),
        user_id=str(current_user.id),
        user_email=current_user.email,
    )
    return SubstitutionResponse.model_validate(substitution)


@router.delete(
    "/{substitution_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_operacional_permission(Permission.SUBSTITUTIONS_CREATE)],
)
async def delete_substitution(
    substitution_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove uma substituição (soft delete).

    Só é possível deletar substituições pendentes.
    """
    repo = SubstitutionRepository(db)
    deleted = await repo.delete(substitution_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Substituição não encontrada ou não pode ser deletada",
        )

    logger.info(
        "Substituição deletada com sucesso",
        action="delete_substitution",
        substitution_id=substitution_id,
        user_id=str(current_user.id),
        user_email=current_user.email,
    )
