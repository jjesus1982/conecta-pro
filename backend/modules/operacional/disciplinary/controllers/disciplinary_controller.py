"""
Controller (endpoints) para Medidas Administrativas.

Implementa todos os endpoints REST para:
- CRUD de medidas disciplinares
- Workflow de aprovacao e assinatura
- Templates de documentos
- Assinaturas digitais
- Recomendacoes de IA

Author: Conecta PRO Team
Date: 2026-01-18
Quality Score Target: 99+/100
"""

import asyncio
from datetime import date
from uuid import UUID  # [Operacoes] tipar path id -> 500 (uuid cast) vira 422

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_tenant_id
from core.auth.dependencies import CurrentActiveUser, require_permission

# Gerir medidas disciplinares (decisão do Jordan 2026-07-14): SÓ Jordan, Pyetra (admin,
# passam automático), Gonzaga e Paiva (têm a permissão explícita). Gate por PERMISSÃO — não
# por papel — pra que suporte (Pedro) tenha acesso amplo SEM poder gerir disciplinar.
_PERM_DISCIPLINAR = "gestao:disciplinar_comunicados"
from core.cache import cache_response
from core.database import get_db
from core.logging import logger
from modules.operacional.disciplinary.models import (
    DisciplinaryActionStatus,
    DisciplinaryActionType,
    ReasonCategory,
)
from modules.operacional.disciplinary.schemas import (
    ApproveRequest,
    # DisciplinaryAction
    DisciplinaryActionCreate,
    DisciplinaryActionDetailResponse,
    DisciplinaryActionListResponse,
    DisciplinaryActionResponse,
    DisciplinaryActionUpdate,
    DisciplinaryFilter,
    DisciplinaryStats,
    GenerateDocumentRequest,
    GenerateDocumentResponse,
    LegalComplianceRequest,
    LegalComplianceResponse,
    ProportionalityCheckRequest,
    ProportionalityCheckResponse,
    # AI Advisor
    RecommendationRequest,
    RecommendationResponse,
    RefuseSignRequest,
    RejectRequest,
    # Signature
    SignatureResponse,
    SignatureVerifyRequest,
    SignatureVerifyResponse,
    SignRequest,
    # Workflow
    SubmitForApprovalRequest,
    # Template
    TemplateCreate,
    TemplateListResponse,
    TemplateResponse,
    TemplateUpdate,
)
from modules.operacional.disciplinary.services import (
    get_disciplinary_advisor,
    get_disciplinary_service,
    get_signature_service,
    get_template_service,
)
from modules.operacional.disciplinary.services.disciplinary_service import (
    DisciplinaryNotFoundError,
    DisciplinaryServiceError,
    DisciplinaryValidationError,
    DisciplinaryWorkflowError,
)
from modules.operacional.disciplinary.services.signature_service import (
    SignatureNotFoundError,
    SignatureValidationError,
)
from modules.operacional.disciplinary.services.template_service import (
    TemplateNotFoundError,
)
from modules.operacional.publishers import publish_medida_disciplinar_criada

router = APIRouter(
    tags=["Operacional - Medidas Administrativas"],
    dependencies=[Depends(require_permission(_PERM_DISCIPLINAR))],
)

# =============================================================================
# MEDIDAS DISCIPLINARES - CRUD
# =============================================================================


@router.post(
    "/medidas-administrativas",
    response_model=DisciplinaryActionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar medida disciplinar",
    description="Cria uma nova medida disciplinar (advertencia, suspensao ou justa causa)",
)
async def create_disciplinary_action(
    data: DisciplinaryActionCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> DisciplinaryActionResponse:
    """Cria uma nova medida disciplinar."""
    try:
        service = get_disciplinary_service(db)
        action = await service.create(
            data=data,
            tenant_id=get_tenant_id(current_user),
            created_by=current_user.id,
        )

        logger.info(
            "Medida disciplinar criada com sucesso",
            action="create_disciplinary_action",
            action_id=str(action.id),
            action_code=action.code,
            user_id=str(current_user.id),
            tenant_id=get_tenant_id(current_user),
        )

        asyncio.create_task(
            publish_medida_disciplinar_criada(
                action_id=str(action.id),
                employee_id=str(getattr(data, "employee_id", "") or ""),
                action_type=str(getattr(data, "action_type", "") or ""),
                cliente_id=str(getattr(data, "client_id", "") or ""),
            )
        )

        return DisciplinaryActionResponse.model_validate(action)

    except DisciplinaryValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except DisciplinaryServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/medidas-administrativas",
    response_model=DisciplinaryActionListResponse,
    summary="Listar medidas disciplinares",
    description="Lista medidas disciplinares com filtros e paginacao",
)
async def list_disciplinary_actions(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Pagina atual"),
    page_size: int = Query(20, ge=1, le=100, description="Itens por pagina"),
    action_type: DisciplinaryActionType | None = None,
    status_filter: DisciplinaryActionStatus | None = Query(None, alias="status"),
    reason_category: ReasonCategory | None = None,
    employee_id: str | None = None,
    post_id: str | None = None,
    client_id: str | None = None,
    incident_date_from: date | None = None,
    incident_date_to: date | None = None,
    search: str | None = None,
) -> DisciplinaryActionListResponse:
    """Lista medidas disciplinares com filtros."""
    service = get_disciplinary_service(db)

    filters = DisciplinaryFilter(
        action_type=action_type,
        status=status_filter,
        reason_category=reason_category,
        employee_id=employee_id,
        post_id=post_id,
        client_id=client_id,
        incident_date_from=incident_date_from,
        incident_date_to=incident_date_to,
        search=search,
    )

    return await service.list(
        tenant_id=get_tenant_id(current_user),
        filters=filters,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/medidas-administrativas/estatisticas",
    response_model=DisciplinaryStats,
    summary="Estatisticas de medidas",
    description="Obtem estatisticas de medidas disciplinares",
)
@cache_response(ttl=240, prefix="api:disciplinary")  # 4 minutos
async def get_disciplinary_stats(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> DisciplinaryStats:
    """
    Obtem estatisticas de medidas disciplinares.

    Cache: 4 minutos
    """
    service = get_disciplinary_service(db)
    return await service.get_stats(get_tenant_id(current_user))


@router.get(
    "/medidas-administrativas/pendentes",
    response_model=list[DisciplinaryActionResponse],
    summary="Listar pendentes de aprovacao",
    description="Lista medidas pendentes de aprovacao",
)
async def get_pending_approval(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> list[DisciplinaryActionResponse]:
    """Lista medidas pendentes de aprovacao."""
    service = get_disciplinary_service(db)
    actions = await service.get_pending_approval(get_tenant_id(current_user))
    return [DisciplinaryActionResponse.model_validate(a) for a in actions]


@router.get(
    "/medidas-administrativas/funcionario/{employee_id}",
    response_model=list[DisciplinaryActionResponse],
    summary="Historico do funcionario",
    description="Lista historico disciplinar de um funcionario",
)
async def get_employee_history(
    employee_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> list[DisciplinaryActionResponse]:
    """Lista historico disciplinar de um funcionario."""
    service = get_disciplinary_service(db)
    actions = await service.get_employee_history(employee_id, get_tenant_id(current_user))
    return [DisciplinaryActionResponse.model_validate(a) for a in actions]


# =============================================================================
# ROTAS ESTATICAS - devem vir ANTES de /{action_id}
# =============================================================================


@router.post(
    "/medidas-administrativas/gerar-documento",
    response_model=GenerateDocumentResponse,
    summary="Gerar documento",
    description="Gera documento a partir de template",
    status_code=201,
)
async def generate_document(
    current_user: CurrentActiveUser,
    action_id: str = Query(..., description="ID da medida"),
    db: AsyncSession = Depends(get_db),
    request: GenerateDocumentRequest | None = None,
) -> GenerateDocumentResponse:
    """Gera documento a partir de template."""
    try:
        service = get_disciplinary_service(db)
        return await service.generate_document(
            action_id=action_id,
            tenant_id=get_tenant_id(current_user),
            request=request,
        )

    except DisciplinaryNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medida disciplinar nao encontrada",
        )
    except DisciplinaryValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )


# =============================================================================
# TEMPLATES — estáticas antes de /{action_id}
# =============================================================================


@router.get(
    "/medidas-administrativas/templates",
    response_model=TemplateListResponse,
    summary="Listar templates",
    description="Lista templates de documentos disciplinares",
)
async def list_templates(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    action_type: DisciplinaryActionType | None = None,
) -> TemplateListResponse:
    """Lista templates de documentos."""
    service = get_template_service(db)
    return await service.list(
        tenant_id=get_tenant_id(current_user),
        action_type=action_type.value if action_type else None,
    )


@router.post(
    "/medidas-administrativas/templates",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar template",
    description="Cria um novo template de documento",
)
async def create_template(
    data: TemplateCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> TemplateResponse:
    """Cria um novo template."""
    service = get_template_service(db)
    template = await service.create(
        data=data,
        tenant_id=get_tenant_id(current_user),
        created_by=current_user.id,
    )
    return TemplateResponse.model_validate(template)


@router.get(
    "/medidas-administrativas/templates/{template_id}",
    response_model=TemplateResponse,
    summary="Buscar template",
    description="Busca um template por ID",
)
async def get_template(
    template_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> TemplateResponse:
    """Busca template por ID."""
    try:
        service = get_template_service(db)
        template = await service.get_by_id(template_id, get_tenant_id(current_user))
        return TemplateResponse.model_validate(template)

    except TemplateNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template nao encontrado",
        )


@router.patch(
    "/medidas-administrativas/templates/{template_id}",
    response_model=TemplateResponse,
    summary="Atualizar template",
    description="Atualiza um template existente",
)
async def update_template(
    template_id: str,
    data: TemplateUpdate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> TemplateResponse:
    """Atualiza um template."""
    try:
        service = get_template_service(db)
        template = await service.update(
            template_id=template_id,
            tenant_id=get_tenant_id(current_user),
            data=data,
        )
        return TemplateResponse.model_validate(template)

    except TemplateNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template nao encontrado",
        )


@router.delete(
    "/medidas-administrativas/templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remover template",
    description="Remove um template (soft delete)",
)
async def delete_template(
    template_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove um template."""
    try:
        service = get_template_service(db)
        await service.delete(template_id, get_tenant_id(current_user))

    except TemplateNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template nao encontrado",
        )


# =============================================================================
# IA - RECOMENDACOES — estáticas antes de /{action_id}
# =============================================================================


@router.post(
    "/medidas-administrativas/ia/recomendar",
    response_model=RecommendationResponse,
    summary="Obter recomendacao de medida",
    description="Utiliza IA para recomendar tipo de medida baseado no historico",
    status_code=201,
)
async def get_recommendation(
    request: RecommendationRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> RecommendationResponse:
    """Obtem recomendacao de medida disciplinar."""
    advisor = get_disciplinary_advisor(db)
    return await advisor.recommend_action(request, get_tenant_id(current_user))


@router.post(
    "/medidas-administrativas/ia/validar-conformidade",
    response_model=LegalComplianceResponse,
    summary="Validar conformidade legal",
    description="Valida conformidade da medida com CLT",
    status_code=201,
)
async def validate_compliance(
    request: LegalComplianceRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> LegalComplianceResponse:
    """Valida conformidade legal da medida."""
    advisor = get_disciplinary_advisor(db)
    return await advisor.validate_legal_compliance(request, get_tenant_id(current_user))


@router.post(
    "/medidas-administrativas/ia/verificar-proporcionalidade",
    response_model=ProportionalityCheckResponse,
    summary="Verificar proporcionalidade",
    description="Verifica se medida e proporcional ao historico",
    status_code=201,
)
async def check_proportionality(
    request: ProportionalityCheckRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> ProportionalityCheckResponse:
    """Verifica proporcionalidade da medida."""
    advisor = get_disciplinary_advisor(db)
    return await advisor.check_proportionality(request)


# =============================================================================
# ROTAS DINAMICAS — /{action_id} por último
# =============================================================================


@router.get(
    "/medidas-administrativas/{action_id}",
    response_model=DisciplinaryActionDetailResponse,
    summary="Buscar medida por ID",
    description="Busca uma medida disciplinar pelo ID",
)
async def get_disciplinary_action(
    action_id: UUID,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> DisciplinaryActionDetailResponse:
    """Busca medida disciplinar por ID."""
    try:
        service = get_disciplinary_service(db)
        action = await service.get_by_id(action_id, get_tenant_id(current_user))
        return DisciplinaryActionDetailResponse.model_validate(action)

    except DisciplinaryNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medida disciplinar nao encontrada",
        )


@router.patch(
    "/medidas-administrativas/{action_id}",
    response_model=DisciplinaryActionResponse,
    summary="Atualizar medida",
    description="Atualiza uma medida disciplinar (apenas em rascunho ou rejeitada)",
)
async def update_disciplinary_action(
    action_id: str,
    data: DisciplinaryActionUpdate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> DisciplinaryActionResponse:
    """Atualiza uma medida disciplinar."""
    try:
        service = get_disciplinary_service(db)
        action = await service.update(
            action_id=action_id,
            tenant_id=get_tenant_id(current_user),
            data=data,
        )

        logger.info(
            "Medida disciplinar atualizada com sucesso",
            action="update_disciplinary_action",
            action_id=str(action_id),
            action_code=action.code,
            user_id=str(current_user.id),
        )

        return DisciplinaryActionResponse.model_validate(action)

    except DisciplinaryNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medida disciplinar nao encontrada",
        )
    except DisciplinaryWorkflowError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )


@router.delete(
    "/medidas-administrativas/{action_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remover medida",
    description="Remove uma medida disciplinar (soft delete)",
)
async def delete_disciplinary_action(
    action_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove uma medida disciplinar."""
    try:
        service = get_disciplinary_service(db)
        await service.delete(action_id, get_tenant_id(current_user))

        logger.info(
            "Medida disciplinar removida com sucesso",
            action="delete_disciplinary_action",
            action_id=str(action_id),
            user_id=str(current_user.id),
        )

    except DisciplinaryNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medida disciplinar nao encontrada",
        )
    except DisciplinaryWorkflowError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )


# =============================================================================
# WORKFLOW
# =============================================================================


@router.post(
    "/medidas-administrativas/{action_id}/submeter",
    response_model=DisciplinaryActionResponse,
    summary="Submeter para aprovacao",
    description="Submete medida disciplinar para aprovacao",
    status_code=201,
)
async def submit_for_approval(
    action_id: str,
    request: SubmitForApprovalRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> DisciplinaryActionResponse:
    """Submete medida para aprovacao."""
    try:
        service = get_disciplinary_service(db)
        action = await service.submit_for_approval(
            action_id=action_id,
            tenant_id=get_tenant_id(current_user),
            submitted_by=current_user.id,
            notes=request.notes,
        )

        return DisciplinaryActionResponse.model_validate(action)

    except DisciplinaryNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medida disciplinar nao encontrada",
        )
    except DisciplinaryWorkflowError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )


@router.post(
    "/medidas-administrativas/{action_id}/aprovar",
    response_model=DisciplinaryActionResponse,
    summary="Aprovar medida",
    description="Aprova uma medida disciplinar pendente",
    status_code=201,
)
async def approve_action(
    action_id: str,
    request: ApproveRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> DisciplinaryActionResponse:
    """Aprova uma medida disciplinar."""
    try:
        service = get_disciplinary_service(db)
        action = await service.approve(
            action_id=action_id,
            tenant_id=get_tenant_id(current_user),
            approved_by=current_user.id,
            request=request,
        )

        return DisciplinaryActionResponse.model_validate(action)

    except DisciplinaryNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medida disciplinar nao encontrada",
        )
    except DisciplinaryWorkflowError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )


@router.post(
    "/medidas-administrativas/{action_id}/rejeitar",
    response_model=DisciplinaryActionResponse,
    summary="Rejeitar medida",
    description="Rejeita uma medida disciplinar pendente",
    status_code=201,
)
async def reject_action(
    action_id: str,
    request: RejectRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> DisciplinaryActionResponse:
    """Rejeita uma medida disciplinar."""
    try:
        service = get_disciplinary_service(db)
        action = await service.reject(
            action_id=action_id,
            tenant_id=get_tenant_id(current_user),
            rejected_by=current_user.id,
            request=request,
        )

        return DisciplinaryActionResponse.model_validate(action)

    except DisciplinaryNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medida disciplinar nao encontrada",
        )
    except DisciplinaryWorkflowError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )


@router.post(
    "/medidas-administrativas/{action_id}/assinar",
    response_model=SignatureResponse,
    summary="Assinar documento",
    description="Registra assinatura digital no documento",
    status_code=201,
)
async def sign_document(
    action_id: str,
    request: SignRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> SignatureResponse:
    """Registra assinatura digital."""
    try:
        service = get_signature_service(db)
        signature = await service.sign_document(
            action_id=action_id,
            tenant_id=get_tenant_id(current_user),
            signer_id=str(current_user.id),
            signer_name=current_user.name or current_user.email,
            signer_cpf=getattr(current_user, "cpf", None),
            request=request,
        )

        return SignatureResponse.model_validate(signature)

    except SignatureValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )


@router.post(
    "/medidas-administrativas/{action_id}/recusar-assinatura",
    response_model=DisciplinaryActionResponse,
    summary="Registrar recusa de assinatura",
    description="Registra recusa de assinatura do funcionario com testemunhas",
    status_code=201,
)
async def refuse_signature(
    action_id: str,
    request: RefuseSignRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> DisciplinaryActionResponse:
    """Registra recusa de assinatura."""
    try:
        service = get_signature_service(db)
        action = await service.refuse_signature(
            action_id=action_id,
            tenant_id=get_tenant_id(current_user),
            request=request,
        )

        return DisciplinaryActionResponse.model_validate(action)

    except SignatureValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )


# =============================================================================
# ASSINATURAS
# =============================================================================


@router.post(
    "/assinaturas/verificar",
    response_model=SignatureVerifyResponse,
    summary="Verificar assinatura",
    description="Verifica validade de uma assinatura digital",
    status_code=201,
)
async def verify_signature(
    request: SignatureVerifyRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> SignatureVerifyResponse:
    """Verifica validade de assinatura."""
    try:
        service = get_signature_service(db)
        return await service.verify_signature(request, get_tenant_id(current_user))

    except SignatureNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assinatura nao encontrada",
        )


@router.get(
    "/assinaturas/documento/{document_id}",
    response_model=list[SignatureResponse],
    summary="Listar assinaturas do documento",
    description="Lista todas as assinaturas de um documento",
)
async def get_document_signatures(
    document_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> list[SignatureResponse]:
    """Lista assinaturas de um documento."""
    service = get_signature_service(db)
    signatures = await service.get_by_document(document_id, get_tenant_id(current_user))
    return [SignatureResponse.model_validate(s) for s in signatures]


@router.get(
    "/assinaturas/{signature_id}",
    response_model=SignatureResponse,
    summary="Buscar assinatura",
    description="Busca uma assinatura por ID",
)
async def get_signature(
    signature_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> SignatureResponse:
    """Busca assinatura por ID."""
    try:
        service = get_signature_service(db)
        signature = await service.get_by_id(signature_id, get_tenant_id(current_user))
        return SignatureResponse.model_validate(signature)

    except SignatureNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assinatura nao encontrada",
        )
