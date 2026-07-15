"""Controller para eventos de folha de pagamento."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_db
from modules.hr.payroll_integration.models import EventCategory, EventType
from modules.hr.payroll_integration.schemas import (
    EmployeePayrollSummary,
    EventAdjustmentRequest,
    PayrollEventBulkCreate,
    PayrollEventCreate,
    PayrollEventListResponse,
    PayrollEventResponse,
    PayrollEventUpdate,
)
from modules.hr.payroll_integration.services import PayrollEventService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/events", tags=["Payroll Events"])




def _uget(user, key, default=None):
    """Acessa campo do usuário seja objeto User (get_current_user) ou dict — os endpoints
    usavam current_user['x'], que crashava no User ('User' object is not subscriptable)."""
    if isinstance(user, dict):
        return user.get(key, default)
    return getattr(user, key, default)
@router.post(
    "/",
    response_model=PayrollEventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar evento",
)
async def create_event(
    data: PayrollEventCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> PayrollEventResponse:
    """Cria um novo evento de folha."""
    try:
        service = PayrollEventService(db)
        event = await service.create_event(
            data=data,
            condominio_id=_uget(current_user, "condominio_id"),
            user_id=_uget(current_user, "id"),
        )
        logger.info(
            "Evento criado: %s para funcionário %s por %s",
            event.event_code,
            event.employee_id,
            _uget(current_user, "email"),
        )
        return PayrollEventResponse.model_validate(event)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Erro ao criar evento: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao criar evento",
        )


@router.post(
    "/bulk",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Criar eventos em lote",
)
async def create_bulk_events(
    data: PayrollEventBulkCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """Cria múltiplos eventos de folha em lote."""
    try:
        service = PayrollEventService(db)
        result = await service.create_bulk(
            data=data,
            condominio_id=_uget(current_user, "condominio_id"),
            user_id=_uget(current_user, "id"),
        )
        logger.info(
            "Bulk create: %d criados, %d falhas por %s",
            result["created"],
            result["failed"],
            _uget(current_user, "email"),
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Erro ao criar eventos em lote: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao criar eventos",
        )


@router.get(
    "/period/{period_id}",
    response_model=PayrollEventListResponse,
    summary="Listar eventos do período",
)
async def list_period_events(
    period_id: UUID,
    employee_id: UUID | None = Query(None, description="Filtrar por funcionário"),
    event_type: EventType | None = Query(None, description="Tipo de evento"),
    event_category: EventCategory | None = Query(None, description="Categoria"),
    page: int = Query(1, ge=1, description="Página"),
    page_size: int = Query(100, ge=1, le=1000, description="Itens por página"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),  # pylint: disable=unused-argument
) -> PayrollEventListResponse:
    """Lista eventos de um período com filtros."""
    try:
        service = PayrollEventService(db)
        events, total = await service.list_period_events(
            period_id=period_id,
            employee_id=employee_id,
            event_type=event_type,
            event_category=event_category,
            page=page,
            page_size=page_size,
        )
        return PayrollEventListResponse(
            items=[PayrollEventResponse.model_validate(e) for e in events],
            total=total,
            page=page,
            page_size=page_size,
            pages=(total + page_size - 1) // page_size,
        )
    except Exception as e:
        logger.error("Erro ao listar eventos do período %s: %s", period_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao listar eventos",
        )


@router.get(
    "/employee/{employee_id}/period/{period_id}",
    response_model=list[PayrollEventResponse],
    summary="Eventos do funcionário",
)
async def get_employee_events(
    employee_id: UUID,
    period_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[PayrollEventResponse]:
    """Retorna todos eventos de um funcionário no período."""
    try:
        service = PayrollEventService(db)
        events = await service.get_employee_events(employee_id, period_id)
        return [PayrollEventResponse.model_validate(e) for e in events]
    except Exception as e:
        logger.error(
            "Erro ao buscar eventos do funcionário %s: %s",
            employee_id,
            e,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao buscar eventos",
        )


@router.get(
    "/employee/{employee_id}/period/{period_id}/summary",
    response_model=EmployeePayrollSummary,
    summary="Resumo da folha do funcionário",
)
async def get_employee_summary(
    employee_id: UUID,
    period_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),  # pylint: disable=unused-argument
) -> EmployeePayrollSummary:
    """Retorna resumo da folha de um funcionário."""
    try:
        service = PayrollEventService(db)
        summary = await service.get_employee_summary(employee_id, period_id)
        return summary
    except Exception as e:
        logger.error(
            "Erro ao buscar resumo do funcionário %s: %s",
            employee_id,
            e,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao buscar resumo",
        )


@router.get(
    "/period/{period_id}/totals",
    response_model=dict,
    summary="Totais do período",
)
async def get_period_totals(
    period_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict:
    """Retorna totais consolidados do período."""
    try:
        service = PayrollEventService(db)
        totals = await service.get_period_totals(period_id)
        return {
            "period_id": str(period_id),
            "total_earnings": float(totals.get("total_earnings", 0)),
            "total_deductions": float(totals.get("total_deductions", 0)),
            "total_net": float(totals.get("total_net", 0)),
            "total_employees": totals.get("total_employees", 0),
        }
    except Exception as e:
        logger.error("Erro ao buscar totais do período %s: %s", period_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao buscar totais",
        )


@router.get(
    "/period/{period_id}/by-category",
    response_model=dict,
    summary="Eventos por categoria",
)
async def get_events_by_category(
    period_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict:
    """Retorna eventos agrupados por categoria."""
    try:
        service = PayrollEventService(db)
        grouped = await service.get_events_by_category(period_id)
        return {
            category: [PayrollEventResponse.model_validate(e) for e in events] for category, events in grouped.items()
        }
    except Exception as e:
        logger.error("Erro ao agrupar eventos por categoria: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao agrupar eventos",
        )


@router.get(
    "/{event_id}",
    response_model=PayrollEventResponse,
    summary="Buscar evento",
)
async def get_event(
    event_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),  # pylint: disable=unused-argument
) -> PayrollEventResponse:
    """Busca evento por ID."""
    try:
        service = PayrollEventService(db)
        event = await service.get_event(event_id)
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Evento não encontrado",
            )
        return PayrollEventResponse.model_validate(event)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro ao buscar evento %s: %s", event_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao buscar evento",
        )


@router.put(
    "/{event_id}",
    response_model=PayrollEventResponse,
    summary="Atualizar evento",
)
async def update_event(
    event_id: UUID,
    data: PayrollEventUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> PayrollEventResponse:
    """Atualiza evento de folha."""
    try:
        service = PayrollEventService(db)
        event = await service.update_event(event_id, data)
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Evento não encontrado",
            )
        logger.info("Evento atualizado: %s por %s", event_id, _uget(current_user, "email"))
        return PayrollEventResponse.model_validate(event)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro ao atualizar evento %s: %s", event_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao atualizar evento",
        )


@router.post(
    "/{event_id}/adjust",
    response_model=PayrollEventResponse,
    summary="Ajustar valor",
)
async def adjust_event(
    event_id: UUID,
    data: EventAdjustmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> PayrollEventResponse:
    """Ajusta valor de um evento com justificativa."""
    try:
        service = PayrollEventService(db)
        event = await service.adjust_event(
            event_id=event_id,
            data=data,
            user_id=_uget(current_user, "id"),
        )
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Evento não encontrado",
            )
        logger.info(
            "Evento ajustado: %s para %s por %s",
            event_id,
            data.new_value,
            _uget(current_user, "email"),
        )
        return PayrollEventResponse.model_validate(event)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro ao ajustar evento %s: %s", event_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao ajustar evento",
        )


@router.post(
    "/{event_id}/cancel",
    response_model=PayrollEventResponse,
    summary="Cancelar evento",
)
async def cancel_event(
    event_id: UUID,
    reason: str = Query(..., min_length=10, description="Motivo do cancelamento"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> PayrollEventResponse:
    """Cancela evento de folha."""
    try:
        service = PayrollEventService(db)
        event = await service.cancel_event(
            event_id=event_id,
            reason=reason,
            user_id=_uget(current_user, "id"),
        )
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Evento não encontrado",
            )
        logger.info("Evento cancelado: %s por %s", event_id, _uget(current_user, "email"))
        return PayrollEventResponse.model_validate(event)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro ao cancelar evento %s: %s", event_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao cancelar evento",
        )


@router.post(
    "/employee/{employee_id}/period/{period_id}/recalculate",
    response_model=dict,
    summary="Recalcular funcionário",
)
async def recalculate_employee(
    employee_id: UUID,
    period_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """Recalcula folha de um funcionário específico."""
    try:
        service = PayrollEventService(db)
        result = await service.recalculate_employee(
            employee_id=employee_id,
            period_id=period_id,
            condominio_id=_uget(current_user, "condominio_id"),
            user_id=_uget(current_user, "id"),
        )
        logger.info(
            "Folha recalculada: funcionário %s, período %s por %s",
            employee_id,
            period_id,
            _uget(current_user, "email"),
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(
            "Erro ao recalcular funcionário %s: %s",
            employee_id,
            e,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao recalcular",
        )
