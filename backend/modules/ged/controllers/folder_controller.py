"""Controller para Folder."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_db
from modules.ged.models.folder import FolderPermission, FolderType
from modules.ged.schemas.folder import (
    FolderCreate,
    FolderFilter,
    FolderListResponse,
    FolderResponse,
    FolderStats,
    FolderTreeNode,
    FolderUpdate,
)
from modules.ged.services.folder_service import FolderService


def _uid(current_user) -> str:
    """Extrai user id de User object ou dict."""
    return str(current_user.id) if hasattr(current_user, "id") else _uid(current_user)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/folders", tags=["GED - Pastas"])


@router.post("", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
async def create_folder(
    data: FolderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> FolderResponse:
    """Cria uma nova pasta."""
    service = FolderService(db)
    try:
        user_id = (
            str(current_user.id) if hasattr(current_user, "id") else current_user.get("id", current_user.get("sub"))
        )
        data.owner_id = user_id
        data.created_by = user_id
        return await service.create(data)
    except ValueError as e:
        error_msg = str(e)
        # Se é erro de duplicação, retorna 409 Conflict
        if "Já existe uma pasta" in error_msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error_msg) from e
        # Outros erros de validação retornam 400
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg) from e
    except Exception as e:
        logger.error("Erro ao criar pasta: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao criar pasta",
        ) from e


@router.get("/{folder_id:uuid}", response_model=FolderResponse)
async def get_folder(
    folder_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> FolderResponse:
    """Busca pasta por ID."""
    service = FolderService(db)
    folder = await service.get_by_id(str(folder_id))
    if not folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pasta não encontrada")
    return folder


@router.get("/code/{code}", response_model=FolderResponse)
async def get_folder_by_code(
    code: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> FolderResponse:
    """Busca pasta por código."""
    service = FolderService(db)
    folder = await service.get_by_code(code)
    if not folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pasta não encontrada")
    return folder


@router.put("/{folder_id:uuid}", response_model=FolderResponse)
async def update_folder(
    folder_id: UUID,
    data: FolderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> FolderResponse:
    """Atualiza pasta."""
    service = FolderService(db)
    try:
        folder = await service.update(str(folder_id), data)
        if not folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pasta não encontrada")
        return folder
    except ValueError as e:
        error_msg = str(e)
        # Se é erro de duplicação, retorna 409 Conflict
        if "Já existe uma pasta" in error_msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error_msg) from e
        # Outros erros de validação retornam 400
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg) from e
    except Exception as e:
        logger.error("Erro ao atualizar pasta %s: %s", folder_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao atualizar pasta",
        ) from e


@router.delete("/{folder_id:uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    folder_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> None:
    """Remove pasta."""
    service = FolderService(db)
    try:
        if not await service.delete(str(folder_id)):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pasta não encontrada")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("", response_model=FolderListResponse)
@router.get(
    "/", response_model=FolderListResponse, include_in_schema=False
)  # espelho barra-final (redirect_slashes=False)
async def list_folders(
    condominium_id: str | None = Query(None),
    folder_type: FolderType | None = Query(None),
    parent_id: str | None = Query(None),
    is_active: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    order_by: str = Query("created_at"),
    order_desc: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> FolderListResponse:
    """Lista pastas com filtros."""
    service = FolderService(db)
    filters = FolderFilter(
        condominium_id=condominium_id,
        folder_type=folder_type,
        parent_id=parent_id,
        is_active=is_active,
    )
    return await service.list(filters, page, page_size, order_by, order_desc)


@router.get("/root", include_in_schema=False)
@router.get("/root/list", response_model=list[FolderResponse])
async def get_root_folders(
    condominium_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[FolderResponse]:
    """Retorna pastas raiz."""
    service = FolderService(db)
    return await service.get_root_folders(condominium_id)


@router.get("/{folder_id:uuid}/children", response_model=list[FolderResponse])
async def get_children(
    folder_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[FolderResponse]:
    """Retorna subpastas."""
    service = FolderService(db)
    return await service.get_children(str(folder_id))


@router.get("/tree/view", response_model=list[FolderTreeNode])
async def get_tree(
    root_id: str | None = Query(None),
    condominium_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[FolderTreeNode]:
    """Retorna árvore de pastas."""
    service = FolderService(db)
    return await service.get_tree(root_id, condominium_id)


@router.get("/type/{folder_type}", response_model=list[FolderResponse])
async def get_by_type(
    folder_type: FolderType,
    condominium_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[FolderResponse]:
    """Retorna pastas por tipo."""
    service = FolderService(db)
    return await service.get_by_type(folder_type, condominium_id)


@router.post("/{folder_id:uuid}/archive", response_model=FolderResponse, status_code=201)
async def archive_folder(
    folder_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> FolderResponse:
    """Arquiva pasta."""
    service = FolderService(db)
    folder = await service.archive(str(folder_id), _uid(current_user))
    if not folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pasta não encontrada")
    return folder


@router.post("/{folder_id:uuid}/unarchive", response_model=FolderResponse, status_code=201)
async def unarchive_folder(
    folder_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> FolderResponse:
    """Desarquiva pasta."""
    service = FolderService(db)
    folder = await service.unarchive(str(folder_id))
    if not folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pasta não encontrada")
    return folder


@router.post("/{folder_id:uuid}/block", response_model=FolderResponse, status_code=201)
async def block_folder(
    folder_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> FolderResponse:
    """Bloqueia pasta."""
    service = FolderService(db)
    folder = await service.block(str(folder_id))
    if not folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pasta não encontrada")
    return folder


@router.post("/{folder_id:uuid}/unblock", response_model=FolderResponse, status_code=201)
async def unblock_folder(
    folder_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> FolderResponse:
    """Desbloqueia pasta."""
    service = FolderService(db)
    folder = await service.unblock(str(folder_id))
    if not folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pasta não encontrada")
    return folder


@router.post("/{folder_id:uuid}/move", response_model=FolderResponse, status_code=201)
async def move_folder(
    folder_id: UUID,
    new_parent_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> FolderResponse:
    """Move pasta."""
    service = FolderService(db)
    try:
        folder = await service.move(str(folder_id), new_parent_id)
        if not folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pasta não encontrada")
        return folder
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{folder_id:uuid}/permissions/grant", response_model=FolderResponse, status_code=201)
async def grant_permission(
    folder_id: UUID,
    user_id: str = Query(...),
    permission: FolderPermission = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> FolderResponse:
    """Concede permissão."""
    service = FolderService(db)
    folder = await service.grant_permission(str(folder_id), user_id, permission)
    if not folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pasta não encontrada")
    return folder


@router.post("/{folder_id:uuid}/permissions/revoke", response_model=FolderResponse, status_code=201)
async def revoke_permission(
    folder_id: UUID,
    user_id: str = Query(...),
    permission: FolderPermission = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> FolderResponse:
    """Revoga permissão."""
    service = FolderService(db)
    folder = await service.revoke_permission(str(folder_id), user_id, permission)
    if not folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pasta não encontrada")
    return folder


@router.get("/{folder_id:uuid}/permissions/check")
async def check_permission(
    folder_id: UUID,
    user_id: str = Query(...),
    permission: FolderPermission = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict[str, bool]:
    """Verifica permissão."""
    service = FolderService(db)
    has_permission = await service.check_permission(str(folder_id), user_id, permission)
    return {"has_permission": has_permission}


@router.get("/search/query", response_model=list[FolderResponse])
async def search_folders(
    query: str = Query(..., min_length=2),
    condominium_id: str | None = Query(None),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[FolderResponse]:
    """Busca pastas."""
    service = FolderService(db)
    return await service.search(query, condominium_id, limit)


@router.get("/stats/summary", response_model=FolderStats)
async def get_stats(
    condominium_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> FolderStats:
    """Retorna estatísticas."""
    service = FolderService(db)
    return await service.get_stats(condominium_id)


@router.post("/default-structure", include_in_schema=False, status_code=201)
@router.post("/default-structure/create", response_model=list[FolderResponse], status_code=201)
async def create_default_structure(
    condominium_id: str = Query(...),
    owner_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> list[FolderResponse]:
    """Cria estrutura padrão de pastas."""
    service = FolderService(db)
    return await service.create_default_structure(condominium_id, owner_id, _uid(current_user))
