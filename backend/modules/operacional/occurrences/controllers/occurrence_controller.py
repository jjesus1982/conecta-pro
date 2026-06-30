"""
Controller (endpoints) para Occurrence.
"""

import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.cache import cache_response
from core.cache.utils import invalidate_on_create, invalidate_on_delete, invalidate_on_update
from core.database import get_db
from core.logging import logger
from modules.operacional.occurrences.models import (
    OccurrenceCategory,
    OccurrenceSeverity,
    OccurrenceStatus,
    OccurrenceType,
)
from modules.operacional.occurrences.repositories import OccurrenceRepository
from modules.operacional.occurrences.schemas import (
    AttachmentSchema,
    OccurrenceCreate,
    OccurrenceFilter,
    OccurrenceListResponse,
    OccurrenceResolve,
    OccurrenceResponse,
    OccurrenceStats,
    OccurrenceUpdate,
)
from modules.operacional.permissions import Permission, require_operacional_permission
from modules.operacional.publishers import publish_cat_registrada, publish_ocorrencia_registrada

router = APIRouter(prefix="/occurrences", tags=["Operations - Occurrences"])


def parse_date_filter(date_str: str | None) -> datetime | None:
    """
    Faz parse seguro de data em formato ISO.

    Args:
        date_str: String de data no formato ISO (YYYY-MM-DD ou YYYY-MM-DDTHH:MM:SS)

    Returns:
        datetime object ou None se date_str for None

    Raises:
        HTTPException: Se formato de data for inválido
    """
    if not date_str:
        return None

    try:
        from datetime import datetime

        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Formato de data inválido: {date_str}. Use formato ISO (YYYY-MM-DD ou YYYY-MM-DDTHH:MM:SS)",
        )


@router.post(
    "/",
    response_model=OccurrenceResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_operacional_permission(Permission.OCCURRENCES_CREATE)],
)
async def create_occurrence(
    data: OccurrenceCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> OccurrenceResponse:
    """
    Cria uma nova ocorrência disciplinar.

    Registra infração encontrada durante fiscalização/ronda.
    O usuário atual deve ser um gestor/supervisor com permissão.

    Requer autenticação.
    """
    repo = OccurrenceRepository(db)
    occurrence = await repo.create(data, inspector_id=current_user.id)

    # Invalidar cache
    related_entities = []
    if data.post_id:
        related_entities.append(("post", data.post_id))
    if data.employee_id:
        related_entities.append(("employee", data.employee_id))
    await invalidate_on_create("occurrence", related_entities if related_entities else None)

    logger.info(
        "Occurrence criada com sucesso",
        action="create_occurrence",
        occurrence_id=str(occurrence.id),
        post_id=str(data.post_id) if data.post_id else None,
        inspector_id=str(current_user.id),
        inspector_email=current_user.email,
        severity=(data.severity.value if hasattr(data.severity, "value") else data.severity) if data.severity else None,
    )
    asyncio.create_task(
        publish_ocorrencia_registrada(
            ocorrencia_id=str(occurrence.id),
            tipo=(
                occurrence.occurrence_type.value
                if hasattr(occurrence.occurrence_type, "value")
                else occurrence.occurrence_type
            )
            if occurrence.occurrence_type
            else "outros",
            descricao=data.description or "",
            employee_id=str(data.employee_id) if data.employee_id else None,
            cliente_id=None,
            data=str(occurrence.created_at.date()) if occurrence.created_at else None,
        )
    )
    # P4: hook CAT quando categoria é SEGURANCA_TRABALHO
    if occurrence.category == OccurrenceCategory.SEGURANCA_TRABALHO and data.employee_id:
        asyncio.create_task(
            publish_cat_registrada(
                cat_id=str(occurrence.id),
                employee_id=str(data.employee_id),
                funcionario_nome="",
                cliente_id=str(occurrence.post_id) if occurrence.post_id else "",
                data=str(occurrence.created_at.date()) if occurrence.created_at else "",
                numero_cat=str(occurrence.id),
                afastamento=occurrence.severity.value in ("grave", "gravissima") if occurrence.severity else False,
            )
        )
    return OccurrenceResponse.model_validate(occurrence)


@router.get(
    "/",
    response_model=OccurrenceListResponse,
    dependencies=[require_operacional_permission(Permission.OCCURRENCES_VIEW)],
)
async def list_occurrences(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Página atual"),
    page_size: int = Query(20, ge=1, le=100, description="Itens por página"),
    occurrence_type: OccurrenceType | None = None,
    severity: OccurrenceSeverity | None = None,
    category: OccurrenceCategory | None = None,
    status_filter: OccurrenceStatus | None = Query(None, alias="status"),
    employee_id: str | None = None,
    inspector_id: str | None = None,
    post_id: str | None = None,
    patrol_round_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    search: str | None = None,
) -> OccurrenceListResponse:
    """
    Lista ocorrências com filtros e paginação.
    """
    repo = OccurrenceRepository(db)

    filters = OccurrenceFilter(
        occurrence_type=occurrence_type,
        severity=severity,
        category=category,
        status=status_filter,
        employee_id=employee_id,
        inspector_id=inspector_id,
        post_id=post_id,
        patrol_round_id=patrol_round_id,
        date_from=parse_date_filter(date_from),
        date_to=parse_date_filter(date_to),
        search=search,
    )

    occurrences, total = await repo.list(filters=filters, page=page, page_size=page_size)
    total_pages = (total + page_size - 1) // page_size

    logger.info(
        "Ocorrências listadas",
        action="list_occurrences",
        total=total,
        page=page,
        page_size=page_size,
        filters_applied=any(
            [
                occurrence_type,
                severity,
                category,
                status_filter,
                employee_id,
                inspector_id,
                post_id,
                patrol_round_id,
                date_from,
                date_to,
                search,
            ]
        ),
    )

    return OccurrenceListResponse(
        items=[OccurrenceResponse.model_validate(occ) for occ in occurrences],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/stats",
    response_model=OccurrenceStats,
    dependencies=[require_operacional_permission(Permission.OCCURRENCES_VIEW)],
)
@cache_response(ttl=180, prefix="api:occurrence")  # 3 minutos
async def get_occurrence_stats(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> OccurrenceStats:
    """
    Obtém estatísticas de ocorrências.

    Cache: 3 minutos
    """
    repo = OccurrenceRepository(db)
    return await repo.get_stats()


@router.get(
    "/by-post/{post_id}",
    response_model=list[OccurrenceResponse],
    dependencies=[require_operacional_permission(Permission.OCCURRENCES_VIEW)],
)
async def get_occurrences_by_post(
    post_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> list[OccurrenceResponse]:
    """
    Busca ocorrências de um posto específico.
    """
    repo = OccurrenceRepository(db)
    occurrences = await repo.get_by_post(post_id)

    return [OccurrenceResponse.model_validate(occ) for occ in occurrences]


@router.get(
    "/{occurrence_id}",
    response_model=OccurrenceResponse,
    dependencies=[require_operacional_permission(Permission.OCCURRENCES_VIEW)],
)
async def get_occurrence(
    occurrence_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> OccurrenceResponse:
    """
    Busca ocorrência por ID.
    """
    repo = OccurrenceRepository(db)
    occurrence = await repo.get_by_id(occurrence_id)

    if not occurrence:
        logger.warning(
            "Tentativa de acessar ocorrência inexistente",
            action="get_occurrence_not_found",
            occurrence_id=occurrence_id,
            user_id=str(current_user.id),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ocorrência {occurrence_id} não encontrada. Verifique se o ID está correto.",
        )

    return OccurrenceResponse.model_validate(occurrence)


@router.patch(
    "/{occurrence_id}",
    response_model=OccurrenceResponse,
    dependencies=[require_operacional_permission(Permission.OCCURRENCES_EDIT)],
)
async def update_occurrence(
    occurrence_id: str,
    data: OccurrenceUpdate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> OccurrenceResponse:
    """
    Atualiza uma ocorrência.

    Permite atualização parcial dos campos.
    """
    repo = OccurrenceRepository(db)
    occurrence = await repo.update(occurrence_id, data)

    if not occurrence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Não foi possível atualizar. Ocorrência {occurrence_id} não encontrada.",
        )

    # Invalidar cache
    related_entities = []
    if occurrence.post_id:
        related_entities.append(("post", occurrence.post_id))
    if occurrence.employee_id:
        related_entities.append(("employee", occurrence.employee_id))
    await invalidate_on_update("occurrence", occurrence_id, related_entities if related_entities else None)

    logger.info(
        "Occurrence atualizada com sucesso",
        action="update_occurrence",
        occurrence_id=occurrence_id,
        user_id=str(current_user.id),
        user_email=current_user.email,
    )
    return OccurrenceResponse.model_validate(occurrence)


@router.post(
    "/{occurrence_id}/resolve",
    response_model=OccurrenceResponse,
    dependencies=[require_operacional_permission(Permission.OCCURRENCES_RESOLVE)],
)
async def resolve_occurrence(
    occurrence_id: str,
    data: OccurrenceResolve,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> OccurrenceResponse:
    """
    Resolve uma ocorrência.

    Marca como resolvida e registra ações tomadas.
    """
    repo = OccurrenceRepository(db)
    occurrence = await repo.resolve(occurrence_id, data, resolved_by_id=current_user.id)

    if not occurrence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Não foi possível resolver. Ocorrência {occurrence_id} não encontrada ou já resolvida.",
        )

    logger.info(
        "Occurrence resolvida com sucesso",
        action="resolve_occurrence",
        occurrence_id=occurrence_id,
        user_id=str(current_user.id),
        user_email=current_user.email,
    )
    return OccurrenceResponse.model_validate(occurrence)


@router.post(
    "/{occurrence_id}/attachments",
    response_model=OccurrenceResponse,
    dependencies=[require_operacional_permission(Permission.OCCURRENCES_EDIT)],
)
async def add_attachment(
    occurrence_id: str,
    attachment: AttachmentSchema,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> OccurrenceResponse:
    """
    Adiciona anexo a uma ocorrência.

    Anexo deve conter: type, url, name, size (opcional)
    """
    repo = OccurrenceRepository(db)
    occurrence = await repo.add_attachment(
        occurrence_id,
        attachment.model_dump(),
    )

    if not occurrence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Não foi possível adicionar anexo. Ocorrência {occurrence_id} não encontrada.",
        )

    logger.info(
        "Anexo adicionado a occurrence",
        action="add_occurrence_attachment",
        occurrence_id=occurrence_id,
        user_id=str(current_user.id),
        user_email=current_user.email,
    )
    return OccurrenceResponse.model_validate(occurrence)


@router.delete(
    "/{occurrence_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_operacional_permission(Permission.OCCURRENCES_DELETE)],
)
async def delete_occurrence(
    occurrence_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Deleta (soft delete) uma ocorrência.

    A ocorrência não é removida do banco, apenas marcada como inativa.
    """
    repo = OccurrenceRepository(db)

    # Buscar occurrence antes de deletar para invalidar cache relacionado
    occurrence = await repo.get_by_id(occurrence_id)
    if not occurrence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ocorrência {occurrence_id} não encontrada.",
        )

    post_id = occurrence.post_id
    employee_id = occurrence.employee_id

    deleted = await repo.delete(occurrence_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao deletar ocorrência {occurrence_id}.",
        )

    # Invalidar cache
    related_entities = []
    if post_id:
        related_entities.append(("post", post_id))
    if employee_id:
        related_entities.append(("employee", employee_id))
    await invalidate_on_delete("occurrence", occurrence_id, related_entities if related_entities else None)

    logger.info(
        "Occurrence deletada com sucesso",
        action="delete_occurrence",
        occurrence_id=occurrence_id,
        user_id=str(current_user.id),
        user_email=current_user.email,
    )
