"""Controller para regras de cobranca automatica."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_session
from modules.financial.models.billing_rule import BillingFrequency, BillingRuleStatus, BillingType
from modules.financial.repositories.receivable_repository import BillingRuleRepository
from modules.financial.schemas.receivable import (
    BillingRuleCreate,
    BillingRuleFilter,
    BillingRuleResponse,
    BillingRuleUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing-rules", tags=["Regras de Cobranca"])


def get_repository(
    session: AsyncSession = Depends(get_session),
) -> BillingRuleRepository:
    """Retorna instancia do repository."""
    return BillingRuleRepository(session)


@router.post(
    "",
    response_model=BillingRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar regra de cobranca",
)
async def create_billing_rule(
    data: BillingRuleCreate,
    repo: BillingRuleRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> BillingRuleResponse:
    """Cria uma nova regra de cobranca automatica."""
    try:
        rule = await repo.create(data, current_user.id)
        return BillingRuleResponse.model_validate(rule)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao criar regra de cobranca: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao criar regra de cobranca",
        )


@router.get(
    "",
    response_model=list[BillingRuleResponse],
    summary="Listar regras de cobranca",
)
async def list_billing_rules(
    condominio_id: UUID | None = Query(None),
    search: str | None = Query(None, description="Busca no nome"),
    billing_type: str | None = Query(None, alias="type", description="Tipo"),
    frequency: str | None = Query(None, description="Frequencia"),
    status_filter: str | None = Query(None, alias="status", description="Status"),
    is_active: bool | None = Query(None, description="Apenas ativas"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    repo: BillingRuleRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
):
    """Lista regras de cobranca com filtros."""
    filters = BillingRuleFilter(
        search=search,
        billing_type=BillingType(billing_type) if billing_type else None,
        frequency=BillingFrequency(frequency) if frequency else None,
        status=BillingRuleStatus(status_filter) if status_filter else None,
        is_active=is_active,
    )

    rules = await repo.list(condominio_id, filters, skip, limit)
    return [BillingRuleResponse.model_validate(r) for r in rules]


@router.get(
    "/active",
    response_model=list[BillingRuleResponse],
    summary="Regras ativas",
)
async def get_active_rules(
    condominio_id: UUID | None = Query(None),
    repo: BillingRuleRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
):
    """Retorna regras de cobranca ativas."""
    rules = await repo.get_active(condominio_id)
    return [BillingRuleResponse.model_validate(r) for r in rules]


@router.get(
    "/due-for-generation",
    response_model=list[BillingRuleResponse],
    summary="Regras para geracao",
)
async def get_rules_due_for_generation(
    condominio_id: UUID | None = Query(None),
    repo: BillingRuleRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
):
    """Retorna regras que precisam gerar cobrancas."""
    rules = await repo.get_due_for_generation(condominio_id)
    return [BillingRuleResponse.model_validate(r) for r in rules]


@router.get(
    "/{rule_id}",
    response_model=BillingRuleResponse,
    summary="Buscar regra de cobranca",
)
async def get_billing_rule(
    rule_id: UUID,
    repo: BillingRuleRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> BillingRuleResponse:
    """Busca regra de cobranca por ID."""
    rule = await repo.get_by_id(rule_id)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regra de cobranca nao encontrada",
        )
    return BillingRuleResponse.model_validate(rule)


@router.put(
    "/{rule_id}",
    response_model=BillingRuleResponse,
    summary="Atualizar regra de cobranca",
)
async def update_billing_rule(
    rule_id: UUID,
    data: BillingRuleUpdate,
    repo: BillingRuleRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> BillingRuleResponse:
    """Atualiza uma regra de cobranca."""
    try:
        rule = await repo.get_by_id(rule_id)
        if not rule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Regra de cobranca nao encontrada",
            )

        rule = await repo.update(rule, data)
        return BillingRuleResponse.model_validate(rule)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete(
    "/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir regra de cobranca",
)
async def delete_billing_rule(
    rule_id: UUID,
    repo: BillingRuleRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
):
    """Exclui uma regra de cobranca (soft delete)."""
    rule = await repo.get_by_id(rule_id)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regra de cobranca nao encontrada",
        )

    await repo.delete(rule)


@router.post("/{rule_id}/activate", response_model=BillingRuleResponse, summary="Ativar regra", status_code=201)
async def activate_rule(
    rule_id: UUID,
    repo: BillingRuleRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> BillingRuleResponse:
    """Ativa uma regra de cobranca."""
    rule = await repo.get_by_id(rule_id)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regra de cobranca nao encontrada",
        )

    if rule.status == BillingRuleStatus.ATIVA.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Regra ja esta ativa",
        )

    rule.activate()
    await repo.session.commit()
    return BillingRuleResponse.model_validate(rule)


@router.post("/{rule_id}/pause", response_model=BillingRuleResponse, summary="Pausar regra", status_code=201)
async def pause_rule(
    rule_id: UUID,
    reason: str | None = Query(None, description="Motivo da pausa"),
    repo: BillingRuleRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> BillingRuleResponse:
    """Pausa uma regra de cobranca."""
    rule = await repo.get_by_id(rule_id)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regra de cobranca nao encontrada",
        )

    if rule.status != BillingRuleStatus.ATIVA.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apenas regras ativas podem ser pausadas",
        )

    rule.pause(reason)
    await repo.session.commit()
    return BillingRuleResponse.model_validate(rule)


@router.post("/{rule_id}/cancel", response_model=BillingRuleResponse, summary="Cancelar regra", status_code=201)
async def cancel_rule(
    rule_id: UUID,
    reason: str = Query(..., min_length=5, description="Motivo do cancelamento"),
    repo: BillingRuleRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> BillingRuleResponse:
    """Cancela uma regra de cobranca."""
    rule = await repo.get_by_id(rule_id)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regra de cobranca nao encontrada",
        )

    if rule.status == BillingRuleStatus.CANCELADA.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Regra ja esta cancelada",
        )

    rule.cancel(reason)
    await repo.session.commit()
    return BillingRuleResponse.model_validate(rule)


