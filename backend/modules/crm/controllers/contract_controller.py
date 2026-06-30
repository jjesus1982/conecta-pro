"""
Controller (endpoints) para Gestão de Contratos.
"""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from core.logging import logger
from modules.crm.models.contract import (
    ContractStatus,
    ContractType,
    ServiceType,
)
from modules.crm.repositories.contract_repository import ContractRepository
from modules.crm.schemas.contract import (
    ContractAddendumCreate,
    ContractAddendumResponse,
    ContractAddendumSign,
    ContractCreate,
    ContractDetailResponse,
    ContractFilter,
    ContractItemCreate,
    ContractItemResponse,
    ContractItemUpdate,
    ContractListResponse,
    ContractRenewal,
    ContractResponse,
    ContractSLAReportApprove,
    ContractSLAReportCreate,
    ContractSLAReportResponse,
    ContractStats,
    ContractTemplateCreate,
    ContractTemplateListResponse,
    ContractTemplateResponse,
    ContractTemplateUpdate,
    ContractUpdate,
)
from modules.crm.services.contract_service import (
    AdjustmentResult,
    ContractAlert,
    ContractService,
    RenewalResult,
    SLACalculation,
)

router = APIRouter(prefix="/contracts", tags=["CRM - Contracts"])


@router.get("/{contract_id}/pdf")
async def gerar_pdf_contrato(
    contract_id: str,
    current_user: CurrentActiveUser,  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
    salvar: bool = False,
    teste: bool = False,
):
    """Gera o PDF do contrato no padrão visual Conecta Mais (com selo).
    salvar=true: registra no Conecta PRO e devolve link público de download."""
    from types import SimpleNamespace

    from fastapi import Response

    row = (
        (
            await db.execute(
                text("""
        SELECT c.contract_number, c.name, c.description, c.contract_type, c.monthly_value, c.total_value,
               c.start_date, c.end_date, c.auto_renewal, c.renewal_period_months, c.content, c.clauses,
               c.retencao_iss, c.retencao_inss, c.retencao_csll,
               cl.name AS client_name, cl.document_number AS client_document
        FROM contracts c LEFT JOIN clients cl ON cl.id = c.client_id
        WHERE c.contract_number = :k OR c.id::text = :k
    """),
                {"k": contract_id},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")

    from modules.crm.services.contract_pdf import build_contract_pdf

    try:
        pdf_bytes = build_contract_pdf(SimpleNamespace(**dict(row)))
    except Exception as e:  # noqa: BLE001
        logger.exception("Erro ao gerar PDF do contrato %s", contract_id)
        raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {e}") from e

    if salvar:
        from modules.crm.services.docs_registry import salvar_pdf

        return await salvar_pdf(
            db,
            "contrato",
            f"Contrato {row['contract_number']} - {row.get('client_name', '')}",
            pdf_bytes,
            ref_tipo="contract",
            ref_id=contract_id,
            teste=teste,
        )

    fname = f"contrato_{(row['contract_number'] or contract_id).replace('/', '-')}.pdf"
    return Response(
        content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{fname}"'}
    )


# ============== Contract Endpoints ==============


@router.post("", response_model=ContractDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_contract(
    data: ContractCreate,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ContractDetailResponse:
    """
    Cria um novo contrato.

    Requer autenticação. Contrato inicia em status DRAFT.
    """
    repo = ContractRepository(db)
    contract = await repo.create(data, created_by_id=str(current_user.id))
    logger.info(f"Contract criado por {current_user.email}: {contract.contract_number}")
    return ContractDetailResponse.model_validate(contract)


@router.get("", response_model=ContractListResponse)
async def list_contracts(  # pylint: disable=too-many-locals
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Página atual"),
    page_size: int = Query(20, ge=1, le=100, description="Itens por página"),
    status_filter: ContractStatus | None = Query(None, alias="status"),
    contract_type: ContractType | None = None,
    client_id: str | None = None,
    commercial_manager_id: str | None = None,
    account_manager_id: str | None = None,
    has_sla: bool | None = None,
    min_value: float | None = Query(None, ge=0),
    max_value: float | None = Query(None, ge=0),
    search: str | None = None,
) -> ContractListResponse:
    """
    Lista contratos com filtros e paginação.
    """
    repo = ContractRepository(db)

    filters = ContractFilter(
        status=status_filter,
        contract_type=contract_type,
        client_id=client_id,
        commercial_manager_id=commercial_manager_id,
        account_manager_id=account_manager_id,
        has_sla=has_sla,
        min_value=Decimal(str(min_value)) if min_value else None,
        max_value=Decimal(str(max_value)) if max_value else None,
        search=search,
    )

    contracts, total = await repo.list(filters=filters, page=page, page_size=page_size)
    total_pages = (total + page_size - 1) // page_size

    return ContractListResponse(
        items=[ContractResponse.model_validate(c) for c in contracts],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/stats", response_model=ContractStats)
async def get_contract_stats(
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    client_id: str | None = None,
    commercial_manager_id: str | None = None,
) -> ContractStats:
    """
    Obtém estatísticas de contratos.
    """
    repo = ContractRepository(db)
    return await repo.get_stats(
        client_id=client_id,
        commercial_manager_id=commercial_manager_id,
    )


@router.get("/alerts", response_model=list[ContractAlert])
async def get_contract_alerts(
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    days_ahead: int = Query(30, ge=1, le=90),
) -> list[ContractAlert]:
    """
    Obtém alertas de contratos (vencimento, reajuste).
    """
    repo = ContractRepository(db)
    service = ContractService()

    contracts, _ = await repo.list(
        filters=ContractFilter(status=ContractStatus.ACTIVE),
        page=1,
        page_size=1000,
    )

    return service.get_contract_alerts(contracts, days_ahead=days_ahead)


# ============== Contract Template Endpoints (antes de /{contract_id} para evitar captura) ==============


@router.post(
    "/templates",
    response_model=ContractTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_template(
    data: ContractTemplateCreate,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ContractTemplateResponse:
    """
    Cria template de contrato.
    """
    repo = ContractRepository(db)
    template = await repo.create_template(data)
    logger.info(f"Template criado por {current_user.email}: {template.name}")
    return ContractTemplateResponse.model_validate(template)


@router.get("/templates", response_model=ContractTemplateListResponse)
async def list_templates(
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    service_type: ServiceType | None = None,
    approved_only: bool = False,
) -> ContractTemplateListResponse:
    """
    Lista templates de contrato.
    """
    repo = ContractRepository(db)
    templates = await repo.list_templates(
        service_type=service_type.value if service_type else None,
        approved_only=approved_only,
    )
    return ContractTemplateListResponse(
        items=[ContractTemplateResponse.model_validate(t) for t in templates],
        total=len(templates),
    )


# ============== Contract by ID (deve vir DEPOIS de rotas estáticas) ==============


@router.get("/{contract_id}", response_model=ContractDetailResponse)
async def get_contract(
    contract_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ContractDetailResponse:
    """
    Obtém um contrato pelo ID com todos os itens.
    """
    repo = ContractRepository(db)
    contract = await repo.get_by_id(contract_id)

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contrato não encontrado",
        )

    return ContractDetailResponse.model_validate(contract)


@router.put("/{contract_id}", response_model=ContractDetailResponse)
async def update_contract(
    contract_id: str,
    data: ContractUpdate,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ContractDetailResponse:
    """
    Atualiza um contrato.

    Apenas contratos em rascunho podem ser editados completamente.
    """
    repo = ContractRepository(db)
    contract = await repo.update(contract_id, data)

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contrato não encontrado ou não pode ser editado",
        )

    logger.info(f"Contract atualizado por {current_user.email}: {contract.contract_number}")
    return ContractDetailResponse.model_validate(contract)


@router.post("/{contract_id}/submit", response_model=ContractResponse, status_code=201)
async def submit_contract_for_signature(
    contract_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ContractResponse:
    """
    Envia contrato para assinatura.

    Muda status de DRAFT para PENDING_SIGNATURE.
    """
    repo = ContractRepository(db)
    contract = await repo.update_status(
        contract_id,
        ContractStatus.PENDING_SIGNATURE,
        user_id=str(current_user.id),
    )

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contrato não encontrado ou não está em rascunho",
        )

    logger.info(f"Contract enviado para assinatura por {current_user.email}: {contract.contract_number}")
    return ContractResponse.model_validate(contract)


@router.post("/{contract_id}/activate", response_model=ContractResponse, status_code=201)
async def activate_contract(
    contract_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ContractResponse:
    """
    Ativa o contrato após assinatura.
    """
    repo = ContractRepository(db)
    contract = await repo.update_status(
        contract_id,
        ContractStatus.ACTIVE,
        user_id=str(current_user.id),
    )

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contrato não encontrado ou não está pendente de assinatura",
        )

    logger.info(f"Contract ativado por {current_user.email}: {contract.contract_number}")

    # Captura valores planos p/ lançar o MRR em sessão isolada (depois dos publishers).
    _mrr_args = (
        contract.contract_number,
        str(getattr(contract.contract_type, "value", contract.contract_type)),
        float(contract.monthly_value or 0),
        contract.name,
        str(contract.client_id) if contract.client_id else None,
        contract.start_date,
    )

    import asyncio

    from modules.crm.publishers import publish_cliente_ativo, publish_contrato_assinado

    asyncio.create_task(
        publish_contrato_assinado(
            contrato_id=str(contract.id),
            numero=contract.contract_number,
            cliente_id=str(getattr(contract, "client_id", "") or ""),
            nome_cliente=str(getattr(contract, "client_name", "") or ""),
            tipo_contrato=str(getattr(contract, "contract_type", "") or ""),
            valor_mensal=float(getattr(contract, "monthly_value", 0) or 0),
            vigencia_inicio=str(getattr(contract, "start_date", "") or ""),
            vigencia_fim=str(getattr(contract, "end_date", "") or ""),
        )
    )
    asyncio.create_task(
        publish_cliente_ativo(
            cliente_id=str(getattr(contract, "client_id", "") or ""),
            nome=str(getattr(contract, "client_name", "") or ""),
            tipo_contrato=str(getattr(contract, "contract_type", "") or ""),
            valor_contrato=float(getattr(contract, "monthly_value", 0) or 0),
        )
    )

    # MRR: contrato ativo recorrente -> lança a linha de faturamento (client_contracts).
    await _bridge_contract_to_billing(*_mrr_args)

    return ContractResponse.model_validate(contract)


@router.post("/{contract_id}/suspend", response_model=ContractResponse, status_code=201)
async def suspend_contract(
    contract_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    reason: str | None = None,  # pylint: disable=unused-argument
) -> ContractResponse:
    """
    Suspende um contrato ativo.
    """
    repo = ContractRepository(db)
    contract = await repo.update_status(
        contract_id,
        ContractStatus.SUSPENDED,
        user_id=str(current_user.id),
    )

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contrato não encontrado ou não pode ser suspenso",
        )

    logger.info(f"Contract suspenso por {current_user.email}: {contract.contract_number}")
    return ContractResponse.model_validate(contract)


@router.post("/{contract_id}/terminate", response_model=ContractResponse, status_code=201)
async def terminate_contract(
    contract_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    reason: str | None = None,  # pylint: disable=unused-argument
) -> ContractResponse:
    """
    Encerra um contrato.
    """
    repo = ContractRepository(db)
    contract = await repo.update_status(
        contract_id,
        ContractStatus.TERMINATED,
        user_id=str(current_user.id),
    )

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contrato não encontrado ou não pode ser encerrado",
        )

    logger.info(f"Contract encerrado por {current_user.email}: {contract.contract_number}")
    return ContractResponse.model_validate(contract)


@router.post("/{contract_id}/renew", response_model=RenewalResult, status_code=201)
async def calculate_renewal(
    contract_id: str,
    data: ContractRenewal,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> RenewalResult:
    """
    Calcula renovação do contrato.

    Retorna simulação sem aplicar alterações.
    """
    repo = ContractRepository(db)
    service = ContractService()

    contract = await repo.get_by_id(contract_id)

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contrato não encontrado",
        )

    return service.calculate_renewal(
        contract=contract,
        custom_adjustment_percent=data.adjustment_percent,
        new_end_date=data.new_end_date,
    )


@router.post("/{contract_id}/calculate-adjustment", response_model=AdjustmentResult, status_code=201)
async def calculate_adjustment(
    contract_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    custom_percent: float | None = None,
    effective_date: date | None = None,
) -> AdjustmentResult:
    """
    Calcula reajuste do contrato.

    Retorna simulação sem aplicar alterações.
    """
    repo = ContractRepository(db)
    service = ContractService()

    contract = await repo.get_by_id(contract_id)

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contrato não encontrado",
        )

    return service.calculate_adjustment(
        contract=contract,
        custom_percent=Decimal(str(custom_percent)) if custom_percent else None,
        effective_date=effective_date,
    )


@router.delete("/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contract(
    contract_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove um contrato (soft delete).

    Apenas contratos em rascunho podem ser excluídos.
    """
    repo = ContractRepository(db)
    deleted = await repo.delete(contract_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contrato não encontrado ou não pode ser excluído",
        )

    logger.info(f"Contract deletado por {current_user.email}: {contract_id}")


# ============== Contract Item Endpoints ==============


@router.post("/{contract_id}/items", response_model=ContractItemResponse, status_code=201)
async def add_contract_item(
    contract_id: str,
    data: ContractItemCreate,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ContractItemResponse:
    """
    Adiciona item ao contrato.
    """
    repo = ContractRepository(db)
    item = await repo.add_item(contract_id, data)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contrato não encontrado ou não pode ser editado",
        )

    logger.info(f"Item adicionado ao contrato {contract_id} por {current_user.email}")
    return ContractItemResponse.model_validate(item)


@router.put("/{contract_id}/items/{item_id}", response_model=ContractItemResponse)
async def update_contract_item(
    contract_id: str,
    item_id: str,
    data: ContractItemUpdate,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ContractItemResponse:
    """
    Atualiza item do contrato.
    """
    repo = ContractRepository(db)
    item = await repo.update_item(contract_id, item_id, data)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item ou contrato não encontrado",
        )

    logger.info(f"Item {item_id} atualizado por {current_user.email}")
    return ContractItemResponse.model_validate(item)


@router.delete(
    "/{contract_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_contract_item(
    contract_id: str,
    item_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove item do contrato.
    """
    repo = ContractRepository(db)
    removed = await repo.remove_item(contract_id, item_id)

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item ou contrato não encontrado",
        )

    logger.info(f"Item {item_id} removido do contrato {contract_id}")


# ============== Contract Addendum Endpoints ==============


@router.post("/{contract_id}/addendums", response_model=ContractAddendumResponse, status_code=201)
async def create_addendum(
    contract_id: str,
    data: ContractAddendumCreate,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ContractAddendumResponse:
    """
    Cria aditivo do contrato.
    """
    repo = ContractRepository(db)
    addendum = await repo.create_addendum(contract_id, data, created_by_id=str(current_user.id))

    if not addendum:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contrato não encontrado ou não está ativo",
        )

    logger.info(f"Aditivo criado por {current_user.email}: {addendum.addendum_number}")
    return ContractAddendumResponse.model_validate(addendum)


@router.get("/{contract_id}/addendums", response_model=list[ContractAddendumResponse])
async def list_addendums(
    contract_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> list[ContractAddendumResponse]:
    """
    Lista aditivos do contrato.
    """
    repo = ContractRepository(db)
    addendums = await repo.list_addendums(contract_id)
    return [ContractAddendumResponse.model_validate(a) for a in addendums]


@router.post("/addendums/{addendum_id}/sign", response_model=ContractAddendumResponse, status_code=201)
async def sign_addendum(
    addendum_id: str,
    data: ContractAddendumSign,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ContractAddendumResponse:
    """
    Assina aditivo e aplica alterações ao contrato.
    """
    repo = ContractRepository(db)
    addendum = await repo.sign_addendum(addendum_id, data.signature_document_id)

    if not addendum:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aditivo não encontrado ou já assinado",
        )

    logger.info(f"Aditivo assinado por {current_user.email}: {addendum.addendum_number}")
    return ContractAddendumResponse.model_validate(addendum)


# (create_template e list_templates movidos para antes de /{contract_id} — ver acima)


@router.get("/templates/{template_id}", response_model=ContractTemplateResponse)
async def get_template(
    template_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ContractTemplateResponse:
    """
    Obtém template por ID.
    """
    repo = ContractRepository(db)
    template = await repo.get_template_by_id(template_id)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template não encontrado",
        )

    return ContractTemplateResponse.model_validate(template)


@router.put("/templates/{template_id}", response_model=ContractTemplateResponse)
async def update_template(
    template_id: str,
    data: ContractTemplateUpdate,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ContractTemplateResponse:
    """
    Atualiza template.
    """
    repo = ContractRepository(db)
    template = await repo.update_template(template_id, data)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template não encontrado",
        )

    logger.info(f"Template atualizado por {current_user.email}: {template.name}")
    return ContractTemplateResponse.model_validate(template)


@router.post("/templates/{template_id}/approve", response_model=ContractTemplateResponse, status_code=201)
async def approve_template(
    template_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ContractTemplateResponse:
    """
    Aprova template juridicamente.
    """
    repo = ContractRepository(db)
    template = await repo.approve_template(template_id, str(current_user.id))

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template não encontrado",
        )

    logger.info(f"Template aprovado por {current_user.email}: {template.name}")
    return ContractTemplateResponse.model_validate(template)


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove template (soft delete).
    """
    repo = ContractRepository(db)
    deleted = await repo.delete_template(template_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template não encontrado",
        )

    logger.info(f"Template deletado por {current_user.email}: {template_id}")


# ============== SLA Report Endpoints ==============


@router.post("/{contract_id}/sla-reports", response_model=ContractSLAReportResponse, status_code=201)
async def create_sla_report(
    contract_id: str,
    data: ContractSLAReportCreate,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ContractSLAReportResponse:
    """
    Cria relatório de SLA mensal.
    """
    repo = ContractRepository(db)
    report = await repo.create_sla_report(contract_id, data, generated_by_id=str(current_user.id))

    if not report:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contrato não encontrado, não tem SLA, ou relatório já existe",
        )

    logger.info(f"SLA Report criado por {current_user.email}: {report.period_label}")
    return ContractSLAReportResponse.model_validate(report)


@router.get("/{contract_id}/sla-reports", response_model=list[ContractSLAReportResponse])
async def list_sla_reports(
    contract_id: str,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    year: int | None = None,
) -> list[ContractSLAReportResponse]:
    """
    Lista relatórios de SLA do contrato.
    """
    repo = ContractRepository(db)
    reports = await repo.list_sla_reports(contract_id, year=year)
    return [ContractSLAReportResponse.model_validate(r) for r in reports]


@router.post("/sla-reports/{report_id}/approve", response_model=ContractSLAReportResponse, status_code=201)
async def approve_sla_report(
    report_id: str,
    data: ContractSLAReportApprove,
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> ContractSLAReportResponse:
    """
    Aprova ou disputa relatório de SLA.
    """
    repo = ContractRepository(db)
    report = await repo.approve_sla_report(
        report_id,
        approved_by_id=str(current_user.id),
        disputed=data.disputed,
    )

    if not report:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Relatório não encontrado ou não está em rascunho",
        )

    action = "disputado" if data.disputed else "aprovado"
    logger.info(f"SLA Report {action} por {current_user.email}: {report.period_label}")
    return ContractSLAReportResponse.model_validate(report)


@router.post("/{contract_id}/calculate-sla", response_model=SLACalculation, status_code=201)
async def calculate_sla(
    contract_id: str,
    indicator_results: list[dict],
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
) -> SLACalculation:
    """
    Calcula SLA do contrato baseado nos indicadores.

    Retorna simulação sem salvar relatório.
    """
    repo = ContractRepository(db)
    service = ContractService()

    contract = await repo.get_by_id(contract_id)

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contrato não encontrado",
        )

    return service.calculate_sla(contract, indicator_results)


# ============================================================================
# ATIVAR CONTRATO -> alimenta o MRR (cria a linha de billing em client_contracts)
# ============================================================================


async def _bridge_contract_to_billing(num, ctype_val, monthly, name, client_id, start_date) -> bool:
    """Cria a linha de faturamento (client_contracts) p/ entrar no MRR, em SESSÃO ISOLADA com
    valores planos (evita MissingGreenlet). Idempotente (dedup por contract_number). Best-effort."""
    try:
        monthly = float(monthly or 0)
        if str(ctype_val or "").lower() != "recurring" or monthly <= 0 or not client_id:
            return False
        nome = (name or "").lower()
        if "cerca" in nome:
            st = "cerca_eletrica"
        elif "cftv" in nome or "câmera" in nome or "camera" in nome:
            st = "cftv"
        elif "monitor" in nome:
            st = "monitoramento_24h"
        elif "alarme" in nome:
            st = "alarme"
        else:
            st = "portaria_remota"

        from core.database import async_session_factory

        async with async_session_factory() as s:
            existing = (
                await s.execute(text("SELECT id FROM client_contracts WHERE contract_number = :n LIMIT 1"), {"n": num})
            ).first()
            if existing:
                return False
            await s.execute(
                text("""
                INSERT INTO client_contracts
                    (id, client_id, contract_number, service_type, status, monthly_value, start_date,
                     auto_renewal, ativo, created_at, updated_at)
                VALUES
                    (gen_random_uuid(), :cid, :num, CAST(:st AS contract_service_type_enum),
                     CAST('active' AS service_status_enum), :mv, :sd, true, true, now(), now())
                """),
                {"cid": client_id, "num": num, "st": st, "mv": monthly, "sd": start_date or date.today()},
            )
            await s.execute(
                text("UPDATE clients SET mrr = COALESCE(mrr, 0) + :mv WHERE id = :cid"),
                {"mv": monthly, "cid": client_id},
            )
            await s.commit()
        logger.info(f"MRR: contrato {num} -> billing client_contracts (R$ {monthly}/mês)")
        return True
    except Exception as exc:  # noqa: BLE001 — bridge nunca quebra a ativação
        logger.warning(f"Bridge contrato->MRR falhou ({num}): {exc}")
        return False
