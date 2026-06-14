"""
Controller (endpoints) para Proposal.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from core.logging import logger
from modules.crm.models.proposal import ProposalStatus, ProposalType
from modules.crm.repositories.proposal_repository import ProposalRepository
from modules.crm.schemas.proposal import (
    ProposalApprovalRequest,
    ProposalCreate,
    ProposalCreateFromOpportunity,
    ProposalDetailResponse,
    ProposalFilter,
    ProposalItemCreate,
    ProposalItemResponse,
    ProposalListResponse,
    ProposalResponse,
    ProposalStats,
    ProposalTemplateCreate,
    ProposalTemplateResponse,
    ProposalTemplateUpdate,
    ProposalUpdate,
)

router = APIRouter(prefix="/proposals", tags=["CRM - Proposals"])


# ============== Proposal Endpoints ==============


@router.post("", response_model=ProposalDetailResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=ProposalDetailResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def create_proposal(
    data: ProposalCreate,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ProposalDetailResponse:
    """
    Cria uma nova proposta comercial.

    Requer autenticacao. Totais sao calculados automaticamente.
    """
    repo = ProposalRepository(db)
    proposal = await repo.create(data, created_by_id=str(current_user.id))
    logger.info(f"Proposal criada por {current_user.email}: {proposal.number}")
    return ProposalDetailResponse.model_validate(proposal)


@router.post(
    "/from-opportunity",
    response_model=ProposalDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_proposal_from_opportunity(
    data: ProposalCreateFromOpportunity,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ProposalDetailResponse:
    """
    Cria proposta a partir de uma opportunity.

    Dados do cliente sao copiados da opportunity.
    """
    repo = ProposalRepository(db)
    proposal = await repo.create_from_opportunity(data, created_by_id=str(current_user.id))

    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Opportunity nao encontrada ou inativa",
        )

    logger.info(f"Proposal criada de opportunity {data.opportunity_id} por {current_user.email}: {proposal.number}")
    return ProposalDetailResponse.model_validate(proposal)


@router.get("", response_model=ProposalListResponse)
@router.get("/", response_model=ProposalListResponse, include_in_schema=False)
async def list_proposals(  # pylint: disable=too-many-locals
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Pagina atual"),
    page_size: int = Query(20, ge=1, le=100, description="Itens por pagina"),
    status_filter: ProposalStatus | None = Query(None, alias="status"),
    proposal_type: ProposalType | None = None,
    opportunity_id: str | None = None,
    is_expired: bool | None = None,
    min_value: float | None = Query(None, ge=0),
    max_value: float | None = Query(None, ge=0),
    client_name: str | None = None,
    search: str | None = None,
) -> ProposalListResponse:
    """
    Lista propostas com filtros e paginacao.

    Suporta busca por numero, titulo, cliente.
    """
    repo = ProposalRepository(db)

    filters = ProposalFilter(
        status=status_filter,
        proposal_type=proposal_type,
        opportunity_id=opportunity_id,
        is_expired=is_expired,
        min_value=min_value,
        max_value=max_value,
        client_name=client_name,
        search=search,
    )

    proposals, total = await repo.list(filters=filters, page=page, page_size=page_size)

    total_pages = (total + page_size - 1) // page_size

    return ProposalListResponse(
        items=[ProposalResponse.model_validate(p) for p in proposals],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/stats", response_model=ProposalStats)
async def get_proposal_stats(
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    created_by_id: str | None = None,
) -> ProposalStats:
    """
    Obtem estatisticas de propostas.

    Inclui: taxa de aceitacao, valor medio, tempo de resposta.
    """
    repo = ProposalRepository(db)
    return await repo.get_stats(created_by_id=created_by_id)


# ============== Template Endpoints (antes de /{proposal_id} — evita captura de rota) ==============


@router.post(
    "/templates",
    response_model=ProposalTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_template(
    data: ProposalTemplateCreate,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ProposalTemplateResponse:
    """
    Cria template de proposta.
    """
    repo = ProposalRepository(db)
    template = await repo.create_template(data)
    logger.info(f"Template criado por {current_user.email}: {template.name}")
    return ProposalTemplateResponse.model_validate(template)


@router.get("/templates", response_model=list[ProposalTemplateResponse])
async def list_templates(
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> list[ProposalTemplateResponse]:
    """
    Lista todos os templates ativos.
    """
    repo = ProposalRepository(db)
    templates = await repo.list_templates()
    return [ProposalTemplateResponse.model_validate(t) for t in templates]


@router.get("/templates/{template_id}", response_model=ProposalTemplateResponse)
async def get_template(
    template_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ProposalTemplateResponse:
    """
    Obtem template por ID.
    """
    repo = ProposalRepository(db)
    template = await repo.get_template_by_id(template_id)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template nao encontrado",
        )

    return ProposalTemplateResponse.model_validate(template)


@router.put("/templates/{template_id}", response_model=ProposalTemplateResponse)
async def update_template(
    template_id: str,
    data: ProposalTemplateUpdate,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ProposalTemplateResponse:
    """
    Atualiza template.
    """
    repo = ProposalRepository(db)
    template = await repo.update_template(template_id, data)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template nao encontrado",
        )

    logger.info(f"Template atualizado por {current_user.email}: {template.name}")
    return ProposalTemplateResponse.model_validate(template)


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove template (soft delete).
    """
    repo = ProposalRepository(db)
    deleted = await repo.delete_template(template_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template nao encontrado",
        )

    logger.info(f"Template deletado por {current_user.email}: {template_id}")


@router.get("/{proposal_id}", response_model=ProposalDetailResponse)
async def get_proposal(
    proposal_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ProposalDetailResponse:
    """
    Obtem uma proposta pelo ID com todos os itens.
    """
    repo = ProposalRepository(db)
    proposal = await repo.get_by_id(proposal_id)

    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proposta nao encontrada",
        )

    return ProposalDetailResponse.model_validate(proposal)


@router.put("/{proposal_id}", response_model=ProposalDetailResponse)
async def update_proposal(
    proposal_id: str,
    data: ProposalUpdate,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ProposalDetailResponse:
    """
    Atualiza uma proposta.

    Apenas propostas em rascunho ou revisao podem ser editadas.
    """
    repo = ProposalRepository(db)
    proposal = await repo.update(proposal_id, data)

    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proposta nao encontrada ou nao pode ser editada",
        )

    logger.info(f"Proposal atualizada por {current_user.email}: {proposal.number}")
    return ProposalDetailResponse.model_validate(proposal)


@router.post("/{proposal_id}/submit", response_model=ProposalResponse, status_code=201)
async def submit_proposal_for_approval(
    proposal_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ProposalResponse:
    """
    Submete proposta para aprovacao.

    Muda status de DRAFT para PENDING_APPROVAL.
    """
    repo = ProposalRepository(db)
    proposal = await repo.submit_for_approval(proposal_id, str(current_user.id))

    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Proposta nao encontrada ou nao esta em rascunho",
        )

    logger.info(f"Proposal submetida por {current_user.email}: {proposal.number}")
    return ProposalResponse.model_validate(proposal)


@router.post("/{proposal_id}/approve", response_model=ProposalResponse, status_code=201)
async def process_proposal_approval(
    proposal_id: str,
    data: ProposalApprovalRequest,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ProposalResponse:
    """
    Processa aprovacao/rejeicao de proposta.

    Acoes: approve, reject, request_changes.
    """
    repo = ProposalRepository(db)
    proposal = await repo.process_approval(proposal_id, data, str(current_user.id))

    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Proposta nao encontrada ou nao esta pendente",
        )

    logger.info(f"Proposal {proposal.number} {data.action.value} por {current_user.email}")
    return ProposalResponse.model_validate(proposal)


@router.post("/{proposal_id}/send", response_model=ProposalResponse, status_code=201)
async def send_proposal(
    proposal_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ProposalResponse:
    """
    Marca proposta como enviada ao cliente.

    Muda status para SENT e registra data de envio.
    """
    repo = ProposalRepository(db)
    proposal = await repo.update_status(proposal_id, ProposalStatus.SENT, user_id=str(current_user.id))

    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proposta nao encontrada",
        )

    logger.info(f"Proposal enviada por {current_user.email}: {proposal.number}")
    return ProposalResponse.model_validate(proposal)


async def _try_generate_commission(db: AsyncSession, proposal, created_by_id: str | None) -> None:
    """
    Gera comissão automaticamente quando uma proposta é aceita.

    Defensivo por design: qualquer falha (sem regra, sem vendedor, sem valor)
    apenas registra warning e NUNCA quebra o fluxo de aceite da proposta.
    """
    try:
        from modules.crm.repositories.commission_repository import CommissionRepository
        from modules.crm.schemas.commission import CommissionCreate

        seller_id = getattr(proposal, "created_by_id", None) or created_by_id
        sale_value = float(getattr(proposal, "total", 0) or 0)
        if not seller_id or sale_value <= 0:
            logger.info(
                f"Comissão não gerada p/ proposta {proposal.number}: "
                f"sem vendedor ou valor (seller={seller_id}, total={sale_value})"
            )
            return

        crepo = CommissionRepository(db)
        rules = await crepo.get_valid_rules(seller_id=str(seller_id))
        if not rules:
            logger.info(
                f"Comissão não gerada p/ proposta {proposal.number}: "
                "nenhuma regra de comissão válida cadastrada"
            )
            return

        rule = crepo.service.find_applicable_rule(rules, sale_value) if getattr(crepo, "service", None) else rules[0]
        commission = await crepo.create(
            CommissionCreate(
                seller_id=str(seller_id),
                proposal_id=str(proposal.id),
                sale_value=sale_value,
                rule_id=str(rule.id) if rule else None,
                description=f"Comissão auto — proposta {proposal.number}",
            ),
            created_by_id=created_by_id,
        )
        logger.info(f"Comissão gerada automaticamente: {commission.reference_number} (proposta {proposal.number})")
    except Exception as exc:  # noqa: BLE001 — comissão nunca pode quebrar o aceite
        logger.warning(f"Falha ao gerar comissão p/ proposta {getattr(proposal, 'number', '?')}: {exc}")


@router.post("/{proposal_id}/accept", response_model=ProposalResponse, status_code=201)
async def accept_proposal(
    proposal_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> ProposalResponse:
    """
    Marca proposta como aceita pelo cliente e gera comissão automaticamente
    (se houver vendedor, valor e regra de comissão válida).
    """
    repo = ProposalRepository(db)
    proposal = await repo.update_status(proposal_id, ProposalStatus.ACCEPTED)

    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proposta nao encontrada",
        )

    await _try_generate_commission(db, proposal, str(current_user.id))

    logger.info(f"Proposal aceita: {proposal.number}")
    return ProposalResponse.model_validate(proposal)


@router.post("/{proposal_id}/reject", response_model=ProposalResponse, status_code=201)
async def reject_proposal(
    proposal_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    reason: str | None = None,
) -> ProposalResponse:
    """
    Marca proposta como rejeitada pelo cliente.
    """
    repo = ProposalRepository(db)
    proposal = await repo.update_status(proposal_id, ProposalStatus.REJECTED, notes=reason)

    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proposta nao encontrada",
        )

    logger.info(f"Proposal rejeitada: {proposal.number}")
    return ProposalResponse.model_validate(proposal)


@router.post("/{proposal_id}/new-version", response_model=ProposalDetailResponse, status_code=201)
async def create_new_version(
    proposal_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ProposalDetailResponse:
    """
    Cria nova versao da proposta.

    Mantém mesmo numero, incrementa versao.
    """
    repo = ProposalRepository(db)
    proposal = await repo.create_new_version(proposal_id, str(current_user.id))

    if not proposal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proposta nao encontrada",
        )

    logger.info(f"Nova versao criada por {current_user.email}: {proposal.number} v{proposal.version}")
    return ProposalDetailResponse.model_validate(proposal)


@router.delete("/{proposal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_proposal(
    proposal_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove uma proposta (soft delete).
    """
    repo = ProposalRepository(db)
    deleted = await repo.delete(proposal_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proposta nao encontrada",
        )

    logger.info(f"Proposal deletada por {current_user.email}: {proposal_id}")


# ============== Item Endpoints ==============


@router.post("/{proposal_id}/items", response_model=ProposalItemResponse, status_code=201)
async def add_proposal_item(
    proposal_id: str,
    data: ProposalItemCreate,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ProposalItemResponse:
    """
    Adiciona item a proposta.
    """
    repo = ProposalRepository(db)
    item = await repo.add_item(proposal_id, data)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Proposta nao encontrada ou nao pode ser editada",
        )

    logger.info(f"Item adicionado a proposta {proposal_id} por {current_user.email}")
    return ProposalItemResponse.model_validate(item)


@router.delete(
    "/{proposal_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_proposal_item(
    proposal_id: str,
    item_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove item da proposta.
    """
    repo = ProposalRepository(db)
    removed = await repo.remove_item(proposal_id, item_id)

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item ou proposta nao encontrados",
        )

    logger.info(f"Item {item_id} removido de proposta {proposal_id}")
