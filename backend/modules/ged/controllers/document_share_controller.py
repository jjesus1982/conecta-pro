"""Controller para DocumentShare."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_db
from modules.ged.models.document_share import SharePermission, ShareType
from modules.ged.schemas.document_share import (
    DocumentShareCreate,
    DocumentShareFilter,
    DocumentShareLinkRequest,
    DocumentShareListResponse,
    DocumentShareResponse,
    DocumentShareUpdate,
)
from modules.ged.services.document_share_service import DocumentShareService


def _uid(current_user) -> str:
    """Extrai user id de User object ou dict."""
    return str(current_user.id) if hasattr(current_user, "id") else _uid(current_user)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/document-shares", tags=["GED - Compartilhamento"])


@router.post("", response_model=DocumentShareResponse, status_code=status.HTTP_201_CREATED)
async def create_share(
    data: DocumentShareCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> DocumentShareResponse:
    """Cria compartilhamento."""
    service = DocumentShareService(db)
    try:
        data.shared_by = _uid(current_user)
        return await service.create(data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.error("Erro ao criar compartilhamento: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao criar compartilhamento",
        ) from e


@router.get("/{share_id:uuid}", response_model=DocumentShareResponse)
async def get_share(
    share_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentShareResponse:
    """Busca compartilhamento por ID."""
    service = DocumentShareService(db)
    share = await service.get_by_id(share_id)
    if not share:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compartilhamento não encontrado",
        )
    return share


@router.put("/{share_id:uuid}", response_model=DocumentShareResponse)
async def update_share(
    share_id: str,
    data: DocumentShareUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentShareResponse:
    """Atualiza compartilhamento."""
    service = DocumentShareService(db)
    share = await service.update(share_id, data)
    if not share:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compartilhamento não encontrado",
        )
    return share


@router.delete("/{share_id:uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_share(
    share_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> None:
    """Remove compartilhamento."""
    service = DocumentShareService(db)
    if not await service.delete(share_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compartilhamento não encontrado",
        )


@router.get("", response_model=DocumentShareListResponse)
async def list_shares(
    document_id: str | None = Query(None),
    share_type: ShareType | None = Query(None),
    is_active: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    order_by: str = Query("created_at"),
    order_desc: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentShareListResponse:
    """Lista compartilhamentos."""
    service = DocumentShareService(db)
    filters = DocumentShareFilter(
        document_id=document_id,
        share_type=share_type,
        is_active=is_active,
    )
    return await service.list(filters, page, page_size, order_by, order_desc)


@router.get("/document/{document_id}", response_model=list[DocumentShareResponse])
async def get_by_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[DocumentShareResponse]:
    """Retorna compartilhamentos de um documento."""
    service = DocumentShareService(db)
    return await service.get_by_document(document_id)


@router.get("/owner", include_in_schema=False)
@router.get("/owner/list", response_model=list[DocumentShareResponse])
async def get_by_owner(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> list[DocumentShareResponse]:
    """Retorna compartilhamentos criados pelo usuário."""
    service = DocumentShareService(db)
    return await service.get_by_owner(_uid(current_user), page, page_size)


@router.get("/recipient", include_in_schema=False)
@router.get("/recipient/list", response_model=list[DocumentShareResponse])
async def get_by_recipient(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> list[DocumentShareResponse]:
    """Retorna compartilhamentos recebidos pelo usuário."""
    service = DocumentShareService(db)
    return await service.get_by_recipient(
        recipient_id=_uid(current_user),
        page=page,
        page_size=page_size,
    )


@router.post("/public-link", response_model=DocumentShareResponse, status_code=201)
async def create_public_link(
    data: DocumentShareLinkRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> DocumentShareResponse:
    """Cria link público para documento."""
    service = DocumentShareService(db)
    try:
        data.shared_by = _uid(current_user)
        return await service.create_public_link(data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/link/{token}/access", response_model=DocumentShareResponse)
async def access_by_link(
    token: str,
    password: str | None = Query(None),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
) -> DocumentShareResponse:
    """Acessa documento via link público."""
    service = DocumentShareService(db)
    try:
        ip_address = request.client.host if request else None
        user_agent = request.headers.get("user-agent") if request else None

        return await service.access_by_link(
            token=token,
            password=password,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{share_id:uuid}/revoke", response_model=DocumentShareResponse, status_code=201)
async def revoke_share(
    share_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentShareResponse:
    """Revoga compartilhamento."""
    service = DocumentShareService(db)
    share = await service.revoke(share_id)
    if not share:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compartilhamento não encontrado",
        )
    return share


@router.post("/{share_id:uuid}/accept", response_model=DocumentShareResponse, status_code=201)
async def accept_share(
    share_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> DocumentShareResponse:
    """Aceita compartilhamento."""
    service = DocumentShareService(db)
    share = await service.accept(share_id, _uid(current_user))
    if not share:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compartilhamento não encontrado",
        )
    return share


@router.post("/{share_id:uuid}/reject", response_model=DocumentShareResponse, status_code=201)
async def reject_share(
    share_id: str,
    reason: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentShareResponse:
    """Rejeita compartilhamento."""
    service = DocumentShareService(db)
    share = await service.reject(share_id, reason)
    if not share:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compartilhamento não encontrado",
        )
    return share


@router.post("/{share_id:uuid}/extend", response_model=DocumentShareResponse, status_code=201)
async def extend_expiry(
    share_id: str,
    new_expiry: datetime = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentShareResponse:
    """Estende validade do compartilhamento."""
    service = DocumentShareService(db)
    share = await service.extend_expiry(share_id, new_expiry)
    if not share:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compartilhamento não encontrado",
        )
    return share


@router.post("/{share_id:uuid}/permission", response_model=DocumentShareResponse, status_code=201)
async def update_permission(
    share_id: str,
    permission: SharePermission = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentShareResponse:
    """Atualiza permissão."""
    service = DocumentShareService(db)
    share = await service.update_permission(share_id, permission)
    if not share:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compartilhamento não encontrado",
        )
    return share


@router.post("/{share_id:uuid}/regenerate-token", status_code=201)
async def regenerate_token(
    share_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict:
    """Regenera token de acesso."""
    service = DocumentShareService(db)
    token = await service.regenerate_token(share_id)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compartilhamento não encontrado",
        )
    return {"token": token}


@router.post("/{share_id:uuid}/set-password", response_model=DocumentShareResponse, status_code=201)
async def set_password(
    share_id: str,
    password: str = Query(..., min_length=4),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentShareResponse:
    """Define senha para compartilhamento."""
    service = DocumentShareService(db)
    share = await service.set_password(share_id, password)
    if not share:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compartilhamento não encontrado",
        )
    return share


@router.post("/{share_id:uuid}/remove-password", response_model=DocumentShareResponse, status_code=201)
async def remove_password(
    share_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentShareResponse:
    """Remove senha do compartilhamento."""
    service = DocumentShareService(db)
    share = await service.remove_password(share_id)
    if not share:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compartilhamento não encontrado",
        )
    return share


@router.post("/expire-overdue/run", status_code=201)
async def expire_overdue(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict:
    """Expira compartilhamentos vencidos."""
    service = DocumentShareService(db)
    count = await service.expire_overdue()
    return {"expired_count": count}


@router.get("/{share_id:uuid}/access-log")
async def get_access_log(
    share_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict:
    """Retorna log de acessos."""
    service = DocumentShareService(db)
    log = await service.get_access_log(share_id)
    return {"access_log": log}


@router.get("/stats/summary")
async def get_stats(
    document_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict:
    """Retorna estatísticas."""
    service = DocumentShareService(db)
    return await service.get_stats(document_id)
