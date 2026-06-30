"""
Controller (endpoints) para Opportunity.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from core.logging import logger
from modules.crm.models.opportunity import OpportunityPriority, OpportunityStage
from modules.crm.repositories.opportunity_repository import OpportunityRepository
from modules.crm.schemas.opportunity import (
    OpportunityClose,
    OpportunityCreate,
    OpportunityCreateFromLead,
    OpportunityFilter,
    OpportunityListResponse,
    OpportunityResponse,
    OpportunityStageUpdate,
    OpportunityUpdate,
    PipelineStats,
)
from modules.crm.services.pipeline_sync import ensure_contract_for_won_opportunity
from modules.crm.services.timeline import log_activity

router = APIRouter(prefix="/opportunities", tags=["CRM - Opportunities"])


@router.post("", response_model=OpportunityResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=OpportunityResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def create_opportunity(
    data: OpportunityCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> OpportunityResponse:
    """
    Cria uma nova opportunity.

    Requer autenticacao. O valor ponderado e calculado automaticamente.
    """
    repo = OpportunityRepository(db)
    opportunity = await repo.create(data)
    logger.info(f"Opportunity criada por {current_user.email}: {opportunity.id}")
    return OpportunityResponse.model_validate(opportunity)


@router.post(
    "/from-lead",
    response_model=OpportunityResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_opportunity_from_lead(
    data: OpportunityCreateFromLead,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> OpportunityResponse:
    """
    Converte um lead em opportunity.

    O lead e marcado como WON (convertido) e seus dados sao copiados.
    """
    repo = OpportunityRepository(db)
    opportunity = await repo.create_from_lead(data)

    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead nao encontrado ou inativo",
        )

    logger.info(f"Lead {data.lead_id} convertido em Opportunity {opportunity.id} por {current_user.email}")
    return OpportunityResponse.model_validate(opportunity)


@router.get("", response_model=OpportunityListResponse)
@router.get("/", response_model=OpportunityListResponse, include_in_schema=False)
async def list_opportunities(  # pylint: disable=too-many-locals
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Pagina atual"),
    page_size: int = Query(20, ge=1, le=100, description="Itens por pagina"),
    stage: OpportunityStage | None = None,
    priority: OpportunityPriority | None = None,
    owner_id: str | None = None,
    is_open: bool | None = None,
    min_value: float | None = Query(None, ge=0),
    max_value: float | None = Query(None, ge=0),
    company_name: str | None = None,
    search: str | None = None,
) -> OpportunityListResponse:
    """
    Lista opportunities com filtros e paginacao.

    Suporta busca por titulo, contato, email ou empresa.
    """
    repo = OpportunityRepository(db)

    filters = OpportunityFilter(
        stage=stage,
        priority=priority,
        owner_id=owner_id,
        is_open=is_open,
        min_value=min_value,
        max_value=max_value,
        company_name=company_name,
        search=search,
    )

    opportunities, total = await repo.list(filters=filters, page=page, page_size=page_size)

    total_pages = (total + page_size - 1) // page_size

    return OpportunityListResponse(
        items=[OpportunityResponse.model_validate(opp) for opp in opportunities],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/pipeline/stats", response_model=PipelineStats)
async def get_pipeline_stats(
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    owner_id: str | None = None,
) -> PipelineStats:
    """
    Obtem estatisticas do pipeline de vendas.

    Inclui: valor total, valor ponderado, win rate, tempo medio de fechamento.
    """
    repo = OpportunityRepository(db)
    return await repo.get_pipeline_stats(owner_id=owner_id)


@router.get("/{opportunity_id}", response_model=OpportunityResponse)
async def get_opportunity(
    opportunity_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> OpportunityResponse:
    """
    Obtem uma opportunity pelo ID.
    """
    repo = OpportunityRepository(db)
    opportunity = await repo.get_by_id(opportunity_id)

    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Opportunity nao encontrada",
        )

    return OpportunityResponse.model_validate(opportunity)


@router.put("/{opportunity_id}", response_model=OpportunityResponse)
async def update_opportunity(
    opportunity_id: str,
    data: OpportunityUpdate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> OpportunityResponse:
    """
    Atualiza uma opportunity.

    Apenas campos fornecidos sao atualizados.
    """
    repo = OpportunityRepository(db)
    opportunity = await repo.update(opportunity_id, data)

    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Opportunity nao encontrada",
        )

    logger.info(f"Opportunity atualizada por {current_user.email}: {opportunity.id}")
    return OpportunityResponse.model_validate(opportunity)


@router.patch("/{opportunity_id}/stage", response_model=OpportunityResponse)
async def update_opportunity_stage(
    opportunity_id: str,
    data: OpportunityStageUpdate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> OpportunityResponse:
    """
    Atualiza o estagio de uma opportunity no funil.

    A probabilidade e atualizada automaticamente baseada no estagio.
    """
    repo = OpportunityRepository(db)
    opportunity = await repo.update_stage(opportunity_id, data.stage, data.notes)

    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Opportunity nao encontrada",
        )

    # Ganho pelo Kanban -> cria contrato a partir da proposta vinculada (best-effort).
    await ensure_contract_for_won_opportunity(db, opportunity)
    await log_activity(
        db,
        "deal_stage",
        f"Deal movido para {data.stage.value}",
        opportunity_id=str(opportunity.id),
        lead_id=getattr(opportunity, "lead_id", None),
        user_id=str(current_user.id),
    )
    logger.info(f"Opportunity {opportunity.id} stage alterado para {data.stage.value} por {current_user.email}")
    return OpportunityResponse.model_validate(opportunity)


@router.post("/{opportunity_id}/close", response_model=OpportunityResponse, status_code=201)
async def close_opportunity(
    opportunity_id: str,
    data: OpportunityClose,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> OpportunityResponse:
    """
    Fecha uma opportunity (ganhou ou perdeu).

    Se perdeu, pode informar motivo da perda e concorrente.
    """
    repo = OpportunityRepository(db)
    opportunity = await repo.close(opportunity_id, data)

    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Opportunity nao encontrada",
        )

    # Fechar como Ganho -> cria contrato a partir da proposta vinculada (best-effort).
    await ensure_contract_for_won_opportunity(db, opportunity)
    status_str = "WON" if data.won else "LOST"
    logger.info(f"Opportunity {opportunity.id} fechada como {status_str} por {current_user.email}")
    return OpportunityResponse.model_validate(opportunity)


@router.delete("/{opportunity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_opportunity(
    opportunity_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove uma opportunity (soft delete).
    """
    repo = OpportunityRepository(db)
    deleted = await repo.delete(opportunity_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Opportunity nao encontrada",
        )

    logger.info(f"Opportunity deletada por {current_user.email}: {opportunity_id}")
