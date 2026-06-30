"""Controller para Candidate."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_db
from modules.recruitment.models.candidate import CandidateSource, CandidateStatus
from modules.recruitment.schemas.candidate import (
    CandidateBlock,
    CandidateCreate,
    CandidateFilter,
    CandidateImport,
    CandidateListResponse,
    CandidateResponse,
    CandidateStats,
    CandidateUpdate,
)
from modules.recruitment.services.candidate_service import CandidateService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/candidates", tags=["Recruitment - Candidatos"])


@router.post(
    "/",
    response_model=CandidateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar candidato",
)
async def create_candidate(
    data: CandidateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> CandidateResponse:
    """Cria um novo candidato."""
    service = CandidateService(db)

    try:
        candidate = await service.create(data)
        return CandidateResponse.model_validate(candidate)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao criar candidato: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao criar candidato",
        )


@router.post(
    "/import",
    response_model=CandidateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Importar candidato de currículo",
)
async def import_candidate(
    data: CandidateImport,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> CandidateResponse:
    """Importa candidato a partir do currículo."""
    service = CandidateService(db)

    try:
        candidate = await service.import_from_resume(data)
        return CandidateResponse.model_validate(candidate)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao importar candidato: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao importar candidato",
        )


@router.get("", include_in_schema=False)  # espelho sem barra final (front chama sem barra)
@router.get(
    "/",
    response_model=CandidateListResponse,
    summary="Listar candidatos",
)
async def list_candidates(  # pylint: disable=too-many-locals
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status_filter: CandidateStatus | None = Query(None, alias="status"),
    source: CandidateSource | None = None,
    city: str | None = None,
    state: str | None = None,
    salary_min: float | None = None,
    salary_max: float | None = None,
    search: str | None = None,
    order_by: str = "created_at",
    order_desc: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> CandidateListResponse:
    """Lista candidatos com filtros e paginação."""
    service = CandidateService(db)

    filters = CandidateFilter(
        status=status_filter,
        source=source,
        city=city,
        state=state,
        salary_min=salary_min,
        salary_max=salary_max,
        search=search,
    )

    candidates, total = await service.list_with_filters(filters, skip, limit, order_by, order_desc)

    return CandidateListResponse(
        items=[CandidateResponse.model_validate(c) for c in candidates],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/active",
    response_model=CandidateListResponse,
    summary="Listar candidatos ativos",
)
async def list_active_candidates(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> CandidateListResponse:
    """Lista candidatos ativos e não bloqueados."""
    service = CandidateService(db)
    candidates = await service.get_active(skip, limit)

    return CandidateListResponse(
        items=[CandidateResponse.model_validate(c) for c in candidates],
        total=len(candidates),
        skip=skip,
        limit=limit,
    )


@router.get(
    "/blocked",
    response_model=CandidateListResponse,
    summary="Listar candidatos bloqueados",
)
async def list_blocked_candidates(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> CandidateListResponse:
    """Lista candidatos bloqueados."""
    service = CandidateService(db)
    candidates = await service.get_blocked(skip, limit)

    return CandidateListResponse(
        items=[CandidateResponse.model_validate(c) for c in candidates],
        total=len(candidates),
        skip=skip,
        limit=limit,
    )


@router.get(
    "/search-skills",
    response_model=CandidateListResponse,
    summary="Buscar por habilidades",
)
async def search_by_skills(
    skills: list[str] = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> CandidateListResponse:
    """Busca candidatos por habilidades."""
    service = CandidateService(db)
    candidates = await service.search_by_skills(skills, limit)

    return CandidateListResponse(
        items=[CandidateResponse.model_validate(c) for c in candidates],
        total=len(candidates),
        skip=0,
        limit=limit,
    )


@router.get(
    "/recently-active",
    response_model=CandidateListResponse,
    summary="Candidatos ativos recentemente",
)
async def list_recently_active(
    days: int = Query(30, ge=1, le=90),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> CandidateListResponse:
    """Lista candidatos que tiveram atividade recente."""
    service = CandidateService(db)
    candidates = await service.get_recently_active(days, limit)

    return CandidateListResponse(
        items=[CandidateResponse.model_validate(c) for c in candidates],
        total=len(candidates),
        skip=0,
        limit=limit,
    )


@router.get(
    "/stats",
    response_model=CandidateStats,
    summary="Estatísticas de candidatos",
)
async def get_candidate_stats(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> CandidateStats:
    """Retorna estatísticas dos candidatos."""
    service = CandidateService(db)
    stats = await service.get_stats()
    return CandidateStats(**stats)


@router.get(
    "/{candidate_id}",
    response_model=CandidateResponse,
    summary="Buscar candidato",
)
async def get_candidate(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> CandidateResponse:
    """Busca candidato por ID com relacionamentos."""
    service = CandidateService(db)
    candidate = await service.get_by_id_with_relations(candidate_id)

    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidato não encontrado",
        )

    return CandidateResponse.model_validate(candidate)


@router.get(
    "/email/{email}",
    response_model=CandidateResponse,
    summary="Buscar por email",
)
async def get_candidate_by_email(
    email: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> CandidateResponse:
    """Busca candidato por email."""
    service = CandidateService(db)
    candidate = await service.get_by_email(email)

    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidato não encontrado",
        )

    return CandidateResponse.model_validate(candidate)


@router.put(
    "/{candidate_id}",
    response_model=CandidateResponse,
    summary="Atualizar candidato",
)
async def update_candidate(
    candidate_id: str,
    data: CandidateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> CandidateResponse:
    """Atualiza um candidato existente."""
    service = CandidateService(db)

    try:
        candidate = await service.update(candidate_id, data)
        if not candidate:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Candidato não encontrado",
            )
        return CandidateResponse.model_validate(candidate)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete(
    "/{candidate_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remover candidato",
)
async def delete_candidate(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> None:
    """Remove um candidato (soft delete)."""
    service = CandidateService(db)
    result = await service.delete(candidate_id)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidato não encontrado",
        )


@router.post(
    "/{candidate_id}/block",
    response_model=CandidateResponse,
    summary="Bloquear candidato",
)
async def block_candidate(
    candidate_id: str,
    data: CandidateBlock,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> CandidateResponse:
    """Bloqueia um candidato."""
    service = CandidateService(db)

    candidate = await service.block(candidate_id, data)
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidato não encontrado",
        )

    return CandidateResponse.model_validate(candidate)


@router.post(
    "/{candidate_id}/unblock",
    response_model=CandidateResponse,
    summary="Desbloquear candidato",
)
async def unblock_candidate(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> CandidateResponse:
    """Desbloqueia um candidato."""
    service = CandidateService(db)

    candidate = await service.unblock(candidate_id)
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidato não encontrado",
        )

    return CandidateResponse.model_validate(candidate)


@router.post(
    "/{candidate_id}/archive",
    response_model=CandidateResponse,
    summary="Arquivar candidato",
)
async def archive_candidate(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> CandidateResponse:
    """Arquiva um candidato."""
    service = CandidateService(db)

    candidate = await service.archive(candidate_id)
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidato não encontrado",
        )

    return CandidateResponse.model_validate(candidate)


@router.post(
    "/{candidate_id}/activate",
    response_model=CandidateResponse,
    summary="Ativar candidato",
)
async def activate_candidate(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> CandidateResponse:
    """Ativa um candidato."""
    service = CandidateService(db)

    candidate = await service.activate(candidate_id)
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidato não encontrado",
        )

    return CandidateResponse.model_validate(candidate)


@router.put(
    "/{candidate_id}/tags",
    response_model=CandidateResponse,
    summary="Atualizar tags",
)
async def update_candidate_tags(
    candidate_id: str,
    tags: list[str],
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> CandidateResponse:
    """Atualiza tags do candidato."""
    service = CandidateService(db)

    candidate = await service.update_tags(candidate_id, tags)
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidato não encontrado",
        )

    return CandidateResponse.model_validate(candidate)


@router.post("/{candidate_id}/note", response_model=CandidateResponse, summary="Adicionar nota", status_code=201)
async def add_candidate_note(
    candidate_id: str,
    note: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> CandidateResponse:
    """Adiciona nota ao candidato."""
    service = CandidateService(db)

    author = current_user.get("email", "system")
    candidate = await service.add_note(candidate_id, note, author)
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidato não encontrado",
        )

    return CandidateResponse.model_validate(candidate)


@router.post(
    "/{primary_id}/merge/{secondary_id}",
    response_model=CandidateResponse,
    summary="Mesclar duplicados",
)
async def merge_candidates(
    primary_id: str,
    secondary_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> CandidateResponse:
    """Mescla candidatos duplicados."""
    service = CandidateService(db)

    candidate = await service.merge_duplicates(primary_id, secondary_id)
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidato não encontrado",
        )

    return CandidateResponse.model_validate(candidate)
