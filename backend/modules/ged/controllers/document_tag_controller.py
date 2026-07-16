"""Controller para DocumentTag."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_db
from modules.ged.models.document_tag import TagType
from modules.ged.schemas.document_tag import (
    DocumentTagCreate,
    DocumentTagFilter,
    DocumentTagListResponse,
    DocumentTagResponse,
    DocumentTagTreeNode,
    DocumentTagUpdate,
)
from modules.ged.services.document_tag_service import DocumentTagService


def _uid(current_user) -> str:
    """Extrai user id de User object ou dict."""
    return str(current_user.id) if hasattr(current_user, "id") else _uid(current_user)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/document-tags", tags=["GED - Tags"])


@router.post("", response_model=DocumentTagResponse, status_code=status.HTTP_201_CREATED)
async def create_tag(
    data: DocumentTagCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> DocumentTagResponse:
    """Cria uma nova tag."""
    service = DocumentTagService(db)
    try:
        data.created_by = _uid(current_user)
        return await service.create(data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.error("Erro ao criar tag: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao criar tag",
        ) from e


@router.get("/{tag_id:uuid}", response_model=DocumentTagResponse)
async def get_tag(
    tag_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentTagResponse:
    """Busca tag por ID."""
    service = DocumentTagService(db)
    tag = await service.get_by_id(tag_id)
    if not tag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag não encontrada")
    return tag


@router.get("/name/{name}", response_model=DocumentTagResponse)
async def get_tag_by_name(
    name: str,
    condominium_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentTagResponse:
    """Busca tag por nome."""
    service = DocumentTagService(db)
    tag = await service.get_by_name(name, condominium_id)
    if not tag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag não encontrada")
    return tag


@router.get("/slug/{slug}", response_model=DocumentTagResponse)
async def get_tag_by_slug(
    slug: str,
    condominium_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentTagResponse:
    """Busca tag por slug."""
    service = DocumentTagService(db)
    tag = await service.get_by_slug(slug, condominium_id)
    if not tag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag não encontrada")
    return tag


@router.put("/{tag_id:uuid}", response_model=DocumentTagResponse)
async def update_tag(
    tag_id: str,
    data: DocumentTagUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentTagResponse:
    """Atualiza tag."""
    service = DocumentTagService(db)
    tag = await service.update(tag_id, data)
    if not tag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag não encontrada")
    return tag


@router.delete("/{tag_id:uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> None:
    """Remove tag."""
    service = DocumentTagService(db)
    try:
        if not await service.delete(tag_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag não encontrada")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("", response_model=DocumentTagListResponse)
async def list_tags(
    condominium_id: str | None = Query(None),
    tag_type: TagType | None = Query(None),
    is_active: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    order_by: str = Query("name"),
    order_desc: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentTagListResponse:
    """Lista tags."""
    service = DocumentTagService(db)
    filters = DocumentTagFilter(
        condominium_id=condominium_id,
        tag_type=tag_type,
        is_active=is_active,
    )
    return await service.list(filters, page, page_size, order_by, order_desc)


@router.get("/type/{tag_type}", response_model=list[DocumentTagResponse])
async def get_by_type(
    tag_type: TagType,
    condominium_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[DocumentTagResponse]:
    """Retorna tags por tipo."""
    service = DocumentTagService(db)
    return await service.get_by_type(tag_type, condominium_id)


@router.get("/tree/view", response_model=list[DocumentTagTreeNode])
async def get_tree(
    condominium_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[DocumentTagTreeNode]:
    """Retorna árvore de tags."""
    service = DocumentTagService(db)
    return await service.get_tree(condominium_id)


@router.post("/{tag_id:uuid}/documents/{document_id}/add", status_code=201)
async def add_to_document(
    tag_id: str,
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict:
    """Adiciona tag a documento."""
    service = DocumentTagService(db)
    try:
        result = await service.add_to_document(tag_id, document_id)
        return {"success": result}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.delete("/{tag_id:uuid}/documents/{document_id}", include_in_schema=False)
@router.delete("/{tag_id:uuid}/documents/{document_id}/remove")
async def remove_from_document(
    tag_id: str,
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict:
    """Remove tag de documento."""
    service = DocumentTagService(db)
    result = await service.remove_from_document(tag_id, document_id)
    return {"success": result}


@router.get("/document/{document_id}", response_model=list[DocumentTagResponse])
async def get_by_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[DocumentTagResponse]:
    """Retorna tags de um documento."""
    service = DocumentTagService(db)
    return await service.get_by_document(document_id)


@router.get("/{tag_id:uuid}/documents")
async def get_documents_by_tag(
    tag_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict:
    """Retorna documentos com a tag."""
    service = DocumentTagService(db)
    document_ids = await service.get_documents_by_tag(tag_id, page, page_size)
    return {"document_ids": document_ids, "count": len(document_ids)}


@router.post("/document/{document_id}/set", response_model=list[DocumentTagResponse], status_code=201)
async def set_document_tags(
    document_id: str,
    tag_ids: list[str] = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[DocumentTagResponse]:
    """Define tags de um documento."""
    service = DocumentTagService(db)
    try:
        return await service.set_document_tags(document_id, tag_ids)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/most-used", include_in_schema=False)
@router.get("/most-used/list", response_model=list[DocumentTagResponse])
async def get_most_used(
    condominium_id: str | None = Query(None),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[DocumentTagResponse]:
    """Retorna tags mais usadas."""
    service = DocumentTagService(db)
    return await service.get_most_used(condominium_id, limit)


@router.get("/search/query", response_model=list[DocumentTagResponse])
async def search_tags(
    query: str = Query(..., min_length=1),
    condominium_id: str | None = Query(None),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[DocumentTagResponse]:
    """Busca tags."""
    service = DocumentTagService(db)
    return await service.search(query, condominium_id, limit)


@router.post("/{source_tag_id}/merge/{target_tag_id}", response_model=DocumentTagResponse, status_code=201)
async def merge_tags(
    source_tag_id: str,
    target_tag_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentTagResponse:
    """Mescla duas tags."""
    service = DocumentTagService(db)
    try:
        return await service.merge_tags(source_tag_id, target_tag_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/suggest", response_model=list[DocumentTagResponse], status_code=201)
async def get_suggested_tags(
    text: str = Query(..., min_length=10),
    condominium_id: str | None = Query(None),
    limit: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[DocumentTagResponse]:
    """Sugere tags baseado no texto."""
    service = DocumentTagService(db)
    return await service.get_suggested_tags(text, condominium_id, limit)


@router.post("/default", include_in_schema=False, status_code=201)
@router.post("/default/create", response_model=list[DocumentTagResponse], status_code=201)
async def create_default_tags(
    condominium_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> list[DocumentTagResponse]:
    """Cria tags padrão."""
    service = DocumentTagService(db)
    return await service.create_default_tags(condominium_id, _uid(current_user))


@router.get("/stats/summary")
async def get_stats(
    condominium_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict:
    """Retorna estatísticas."""
    service = DocumentTagService(db)
    return await service.get_stats(condominium_id)
