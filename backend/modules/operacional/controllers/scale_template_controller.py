"""
Controller (endpoints) para ScaleTemplate.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_tenant_id
from core.auth.dependencies import CurrentActiveUser
from core.cache import cache_response
from core.database import get_db
from core.logging import logger
from modules.operacional.permissions import Permission, require_operacional_permission
from modules.operacional.repositories.scale_template_repository import ScaleTemplateRepository
from modules.operacional.schemas.scale import ScaleResponse
from modules.operacional.schemas.scale_template import (
    ScaleTemplateApplyRequest,
    ScaleTemplateCreate,
    ScaleTemplateCreateFromScale,
    ScaleTemplateListResponse,
    ScaleTemplateResponse,
    ScaleTemplateStats,
    ScaleTemplateUpdate,
)
from modules.operacional.services.scale_template_service import ScaleTemplateService

router = APIRouter(prefix="/scales/templates", tags=["Operations - Scale Templates"])


@router.post(
    "/",
    response_model=ScaleTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_operacional_permission(Permission.SCALES_CREATE)],
)
async def create_template(
    data: ScaleTemplateCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> ScaleTemplateResponse:
    """
    Cria um novo template de escala manualmente.

    Permite criar template fornecendo diretamente a estrutura de dados.
    """
    repo = ScaleTemplateRepository(db)

    tenant_id = get_tenant_id(current_user)

    template = await repo.create(
        data=data,
        tenant_id=tenant_id,
        created_by=current_user.id,
    )

    logger.info(f"Template criado por {current_user.email}: {template.id}")
    return ScaleTemplateResponse.model_validate(template)


@router.post(
    "/from-scale",
    response_model=ScaleTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_operacional_permission(Permission.SCALES_CREATE)],
)
async def create_template_from_scale(
    data: ScaleTemplateCreateFromScale,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> ScaleTemplateResponse:
    """
    Cria um template a partir de uma escala existente.

    Extrai a estrutura da escala e salva como template reutilizável.
    """
    service = ScaleTemplateService(db)
    repo = ScaleTemplateRepository(db)

    tenant_id = get_tenant_id(current_user)

    try:
        # Extrair template da escala
        template_data = await service.extract_template_from_scale(
            scale_id=data.scale_id,
            include_employee_mapping=data.include_employee_mapping,
        )

        # Criar template
        create_data = ScaleTemplateCreate(
            name=data.name,
            description=data.description,
            template_data=template_data,
        )

        template = await repo.create(
            data=create_data,
            tenant_id=tenant_id,
            created_by=current_user.id,
        )

        logger.info(f"Template criado a partir da escala {data.scale_id} por {current_user.email}: {template.id}")

        return ScaleTemplateResponse.model_validate(template)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/",
    response_model=ScaleTemplateListResponse,
    dependencies=[require_operacional_permission(Permission.SCALES_VIEW_ALL, Permission.SCALES_VIEW_OWN)],
)
async def list_templates(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Página atual"),
    page_size: int = Query(20, ge=1, le=100, description="Itens por página"),
    include_inactive: bool = Query(False, description="Incluir templates inativos"),
) -> ScaleTemplateListResponse:
    """
    Lista templates de escalas com paginação.
    """
    repo = ScaleTemplateRepository(db)

    tenant_id = get_tenant_id(current_user)

    skip = (page - 1) * page_size
    templates, total = await repo.list(
        tenant_id=tenant_id,
        skip=skip,
        limit=page_size,
        include_inactive=include_inactive,
    )

    total_pages = (total + page_size - 1) // page_size

    return ScaleTemplateListResponse(
        items=[ScaleTemplateResponse.model_validate(t) for t in templates],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/{template_id}",
    response_model=ScaleTemplateResponse,
    dependencies=[require_operacional_permission(Permission.SCALES_VIEW_ALL, Permission.SCALES_VIEW_OWN)],
)
async def get_template(
    template_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> ScaleTemplateResponse:
    """
    Busca template por ID.
    """
    repo = ScaleTemplateRepository(db)

    tenant_id = get_tenant_id(current_user)

    template = await repo.get_by_id(template_id, tenant_id)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template não encontrado",
        )

    return ScaleTemplateResponse.model_validate(template)


@router.patch(
    "/{template_id}",
    response_model=ScaleTemplateResponse,
    dependencies=[require_operacional_permission(Permission.SCALES_CREATE)],
)
async def update_template(
    template_id: str,
    data: ScaleTemplateUpdate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> ScaleTemplateResponse:
    """
    Atualiza um template.
    """
    repo = ScaleTemplateRepository(db)

    tenant_id = get_tenant_id(current_user)

    template = await repo.update(template_id, data, tenant_id)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template não encontrado",
        )

    logger.info(f"Template atualizado por {current_user.email}: {template.id}")
    return ScaleTemplateResponse.model_validate(template)


@router.post(
    "/{template_id}/apply",
    response_model=ScaleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_operacional_permission(Permission.SCALES_CREATE)],
)
async def apply_template(
    template_id: str,
    apply_request: ScaleTemplateApplyRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> ScaleResponse:
    """
    Aplica um template criando nova escala.

    Cria uma nova escala baseada no template para o período especificado.
    Permite mapear novos funcionários e sobrescrever configurações.
    """
    repo = ScaleTemplateRepository(db)
    service = ScaleTemplateService(db)

    tenant_id = get_tenant_id(current_user)

    # Buscar template
    template = await repo.get_by_id(template_id, tenant_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template não encontrado",
        )

    try:
        # Aplicar template
        scale = await service.apply_template_to_period(
            template_data=template.template_data,
            apply_request=apply_request,
            created_by=current_user.id,
        )

        # Incrementar contador de uso
        await repo.increment_usage(template_id)

        logger.info(f"Template {template_id} aplicado por {current_user.email}, escala criada: {scale.id}")

        return ScaleResponse.model_validate(scale)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete(
    "/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_operacional_permission(Permission.SCALES_CREATE)],
)
async def delete_template(
    template_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove um template (soft delete).
    """
    repo = ScaleTemplateRepository(db)

    tenant_id = get_tenant_id(current_user)

    deleted = await repo.delete(template_id, tenant_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template não encontrado",
        )

    logger.info(f"Template deletado por {current_user.email}: {template_id}")
