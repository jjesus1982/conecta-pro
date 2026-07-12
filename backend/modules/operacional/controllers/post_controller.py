"""
Controller (endpoints) para Post.
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text as _sqltext
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.cache import cache_response
from core.database import get_db
from core.logging import logger
from modules.operacional.models.post import PostStatus, PostType, ShiftType
from modules.operacional.permissions import Permission, require_operacional_permission
from modules.operacional.repositories.post_repository import PostRepository
from modules.operacional.schemas.post import (
    PostCreate,
    PostFilter,
    PostListResponse,
    PostResponse,
    PostStats,
    PostUpdate,
)

router = APIRouter(prefix="/posts", tags=["Operations - Posts"])


class DefinirLocalizacaoRequest(BaseModel):
    """Captura da localização REAL do posto (GPS enviado no local pelo líder/supervisor)."""

    lat: float = Field(..., ge=-90, le=90, description="Latitude GPS capturada no posto")
    lng: float = Field(..., ge=-180, le=180, description="Longitude GPS capturada no posto")
    raio_metros: float | None = Field(
        default=None, gt=0, le=5000,
        description="Opcional: raio do geofence em metros (default 150).",
    )


@router.post(
    "/{post_id}/definir-localizacao",
    dependencies=[require_operacional_permission(Permission.POSTS_EDIT)],
)
async def definir_localizacao_posto(
    post_id: UUID,
    current_user: CurrentActiveUser,
    payload: DefinirLocalizacaoRequest = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Grava a localização REAL do posto (lat/lng capturados pelo GPS no local).

    Usado pelo líder/supervisor fisicamente no posto — fonte de verdade do geofence.
    Nunca fabrica coordenada. Também aceita ajustar o raio do geofence.
    """
    exists = (
        await db.execute(
            _sqltext("SELECT name FROM posts WHERE id = :pid"),
            {"pid": str(post_id)},
        )
    ).first()
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Posto não encontrado"
        )

    sets = "latitude = :lat, longitude = :lng, updated_at = now()"
    params: dict[str, Any] = {"pid": str(post_id), "lat": payload.lat, "lng": payload.lng}
    if payload.raio_metros is not None:
        sets += ", geofence_raio_metros = :raio"
        params["raio"] = payload.raio_metros

    await db.execute(
        _sqltext("UPDATE posts SET " + sets + " WHERE id = :pid"), params
    )
    await db.commit()

    logger.info(
        "Localização do posto definida",
        action="definir_localizacao_posto",
        post_id=str(post_id),
        lat=payload.lat,
        lng=payload.lng,
        user_id=str(current_user.id),
    )
    return {
        "post_id": str(post_id),
        "posto_nome": exists[0],
        "latitude": payload.lat,
        "longitude": payload.lng,
        "geofence_raio_metros": payload.raio_metros or 150.0,
        "fonte": "gps_capturado_no_local",
    }


@router.post(
    "/",
    response_model=PostResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_operacional_permission(Permission.POSTS_CREATE)],
)
async def create_post(
    data: PostCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> PostResponse:
    """
    Cria um novo posto de trabalho.

    Requer autenticação.
    """
    repo = PostRepository(db)
    post: Any = await repo.create(data, created_by=current_user.id)

    logger.info(
        "Post criado com sucesso",
        action="create_post",
        post_id=str(post.id),
        user_id=str(current_user.id),
        user_email=current_user.email,
    )
    return PostResponse.model_validate(post)


@router.get(
    "/",
    response_model=PostListResponse,
    dependencies=[require_operacional_permission(Permission.POSTS_VIEW)],
)
async def list_posts(  # pylint: disable=too-many-locals
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Página atual"),
    page_size: int = Query(20, ge=1, le=100, description="Itens por página"),
    post_type: PostType | None = None,
    status_filter: PostStatus | None = Query(None, alias="status"),
    shift_type: ShiftType | None = None,
    contract_id: str | None = None,
    client_id: str | None = None,
    city: str | None = None,
    state: str | None = None,
    requires_armed: bool | None = None,
    requires_vehicle: bool | None = None,
    has_vacancy: bool | None = None,
    search: str | None = None,
) -> PostListResponse:
    """
    Lista postos com filtros e paginação.
    """
    repo = PostRepository(db)

    filters = PostFilter(
        post_type=post_type,
        status=status_filter,
        shift_type=shift_type,
        contract_id=contract_id,
        client_id=client_id,
        city=city,
        state=state,
        requires_armed=requires_armed,
        requires_vehicle=requires_vehicle,
        has_vacancy=has_vacancy,
        search=search,
    )

    posts: list[Any]
    total: int
    posts, total = await repo.list(filters=filters, page=page, page_size=page_size)
    total_pages = (total + page_size - 1) // page_size

    return PostListResponse(
        items=[PostResponse.model_validate(post) for post in posts],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/stats",
    response_model=PostStats,
    dependencies=[require_operacional_permission(Permission.POSTS_VIEW)],
)
@cache_response(ttl=300, prefix="api:post")  # 5 minutos
async def get_post_stats(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> PostStats:
    """
    Obtém estatísticas de postos.

    Cache: 5 minutos
    """
    repo = PostRepository(db)
    return await repo.get_stats()


@router.get(
    "/{post_id}",
    response_model=PostResponse,
    dependencies=[require_operacional_permission(Permission.POSTS_VIEW)],
)
async def get_post(
    post_id: UUID,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> PostResponse:
    """
    Busca posto por ID.
    """
    repo = PostRepository(db)
    post: Any = await repo.get_by_id(str(post_id))

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Posto não encontrado",
        )

    return PostResponse.model_validate(post)


@router.patch(
    "/{post_id}",
    response_model=PostResponse,
    dependencies=[require_operacional_permission(Permission.POSTS_EDIT)],
)
async def update_post(
    post_id: UUID,
    data: PostUpdate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> PostResponse:
    """
    Atualiza um posto.
    """
    repo = PostRepository(db)
    post: Any = await repo.update(str(post_id), data)

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Posto não encontrado",
        )

    logger.info(
        "Post atualizado com sucesso",
        action="update_post",
        post_id=str(post.id),
        user_id=str(current_user.id),
        user_email=current_user.email,
    )
    return PostResponse.model_validate(post)


@router.delete(
    "/{post_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_operacional_permission(Permission.POSTS_DELETE)],
)
async def delete_post(
    post_id: UUID,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove um posto (soft delete).
    """
    repo = PostRepository(db)
    deleted: bool = await repo.delete(str(post_id))

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Posto não encontrado",
        )

    logger.info(
        "Post deletado com sucesso",
        action="delete_post",
        post_id=post_id,
        user_id=str(current_user.id),
        user_email=current_user.email,
    )


@router.get(
    "/contract/{contract_id}",
    response_model=list[PostResponse],
    dependencies=[require_operacional_permission(Permission.POSTS_VIEW)],
)
async def get_posts_by_contract(
    contract_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> list[PostResponse]:
    """
    Lista postos de um contrato.
    """
    repo = PostRepository(db)
    posts: list[Any] = await repo.get_by_contract(contract_id)

    return [PostResponse.model_validate(post) for post in posts]


@router.get(
    "/client/{client_id}",
    response_model=list[PostResponse],
    dependencies=[require_operacional_permission(Permission.POSTS_VIEW)],
)
async def get_posts_by_client(
    client_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> list[PostResponse]:
    """
    Lista postos de um cliente.
    """
    repo = PostRepository(db)
    posts: list[Any] = await repo.get_by_client(client_id)

    return [PostResponse.model_validate(post) for post in posts]
