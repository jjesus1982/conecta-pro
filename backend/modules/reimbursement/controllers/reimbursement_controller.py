"""Controller para endpoints de reembolso."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.reimbursement.models import AttachmentType, ExpenseCategory
from modules.reimbursement.schemas import (
    PaginatedReimbursementResponse,
    ReimbursementApproveRequest,
    ReimbursementAttachmentCreate,
    ReimbursementAttachmentResponse,
    ReimbursementItemCreate,
    ReimbursementItemResponse,
    ReimbursementItemUpdate,
    ReimbursementProcessRequest,
    ReimbursementRejectRequest,
    ReimbursementRequestCreate,
    ReimbursementRequestFilter,
    ReimbursementRequestResponse,
    ReimbursementRequestStats,
    ReimbursementRequestUpdate,
    ReimbursementReturnRequest,
    ReimbursementSubmitRequest,
)
from modules.reimbursement.services import ApprovalService, FileValidator, ReimbursementService

logger = logging.getLogger(__name__)

router = APIRouter()


# Dependência para obter condominio_id do usuário
def get_condominio_id(user: CurrentActiveUser) -> UUID | None:
    """Extrai condominio_id do usuário. Admins retornam None."""
    if hasattr(user, "role") and user.role == "admin":
        return None
    if hasattr(user, "condominio_id") and user.condominio_id:
        return user.condominio_id
    # Em vez de bloquear, retorna None para permitir listagem vazia
    return None


def get_condominio_id_optional(user: CurrentActiveUser) -> UUID | None:
    """Extrai condominio_id do usuário. Retorna None para admins."""
    # Admins podem ver todos os reembolsos
    if hasattr(user, "role") and user.role == "admin":
        return None
    if hasattr(user, "condominio_id") and user.condominio_id:
        return user.condominio_id
    return None


CondominioId = Annotated[UUID, Depends(get_condominio_id)]
CondominioIdOptional = Annotated[UUID | None, Depends(get_condominio_id_optional)]


# ==================== SOLICITAÇÕES ====================


@router.post("/", response_model=ReimbursementRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_reimbursement(
    data: ReimbursementRequestCreate,
    user: CurrentActiveUser,
    condominio_id: CondominioIdOptional,
    db: AsyncSession = Depends(get_db),
):
    """
    Cria uma nova solicitação de reembolso.

    A solicitação é criada em status RASCUNHO.
    Admins precisam ter um condomínio associado ou o sistema usará um padrão.
    """
    service = ReimbursementService(db)

    # Se admin sem condomínio, usa o primeiro condomínio disponível
    if condominio_id is None:
        from modules.reimbursement.repositories import CondominioRepository

        cond_repo = CondominioRepository(db)
        condominio_id = await cond_repo.get_first_active_condominio()

        if not condominio_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nenhum condomínio disponível para criar reembolso",
            )

    request = await service.create_request(condominio_id, user.id, data)
    # Re-fetch após commit para garantir que todos os relacionamentos estão carregados
    fresh = await service.get_request(request.id)
    return fresh


@router.get("/", response_model=PaginatedReimbursementResponse)
async def list_reimbursements(
    user: CurrentActiveUser,
    condominio_id: CondominioIdOptional,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    approval_level: str | None = Query(None),
    expense_date_start: str | None = Query(None),
    expense_date_end: str | None = Query(None),
    search: str | None = Query(None),
    cost_center: str | None = Query(None),
    project: str | None = Query(None),
):
    """Lista todas as solicitações de reembolso (para gestores). Admins veem todos."""
    from datetime import date

    filters = ReimbursementRequestFilter(
        status=status_filter,
        approval_level=approval_level,
        expense_date_start=date.fromisoformat(expense_date_start) if expense_date_start else None,
        expense_date_end=date.fromisoformat(expense_date_end) if expense_date_end else None,
        search=search,
        cost_center=cost_center,
        project=project,
    )

    service = ReimbursementService(db)
    skip = (page - 1) * page_size
    requests, total = await service.list_requests(condominio_id, filters, skip, page_size)

    total_pages = (total + page_size - 1) // page_size

    return PaginatedReimbursementResponse(
        items=requests,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/my", response_model=PaginatedReimbursementResponse)
async def list_my_reimbursements(
    user: CurrentActiveUser,
    condominio_id: CondominioIdOptional,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
):
    """Lista solicitações do usuário autenticado."""
    filters = ReimbursementRequestFilter(status=status_filter)

    service = ReimbursementService(db)
    skip = (page - 1) * page_size
    requests, total = await service.list_my_requests(condominio_id, user.id, filters, skip, page_size)

    total_pages = (total + page_size - 1) // page_size

    return PaginatedReimbursementResponse(
        items=requests,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/stats", response_model=ReimbursementRequestStats)
async def get_stats(
    user: CurrentActiveUser,
    condominio_id: CondominioIdOptional,
    db: AsyncSession = Depends(get_db),
    my_only: bool = Query(False),
):
    """Retorna estatísticas de reembolsos. Admins veem todos."""
    service = ReimbursementService(db)
    requester_id = user.id if my_only else None
    return await service.get_stats(condominio_id, requester_id)


@router.get("/categories")
async def list_categories(
    user: CurrentActiveUser,
    condominio_id: CondominioIdOptional,
    db: AsyncSession = Depends(get_db),
):
    """Lista categorias de reembolso disponíveis. Admins veem todas."""
    service = ReimbursementService(db)
    categories = await service.list_categories(condominio_id)

    # Se não houver categorias customizadas, retorna as padrão
    if not categories:
        return [{"code": e.value, "name": e.value.replace("_", " ").title()} for e in ExpenseCategory]

    return [c.to_dict() for c in categories]


@router.get("/expense-types")
async def list_expense_types():
    """Lista tipos de despesa disponíveis (enum)."""
    return [{"value": e.value, "label": e.value.replace("_", " ").title()} for e in ExpenseCategory]


@router.get("/attachment-types")
async def list_attachment_types():
    """Lista tipos de anexo disponíveis (enum)."""
    return [{"value": e.value, "label": e.value.replace("_", " ").title()} for e in AttachmentType]


@router.get("/ready-for-payment", response_model=PaginatedReimbursementResponse)
async def list_ready_for_payment(
    user: CurrentActiveUser,
    condominio_id: CondominioId,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Lista solicitações aprovadas prontas para pagamento.

    DECLARADA ANTES de /{request_id}: senão o FastAPI tenta casar "ready-for-payment" como UUID
    e retorna 422 (a rota ficava inalcançável).
    """
    service = ApprovalService(db)
    skip = (page - 1) * page_size
    requests, total = await service.list_ready_for_payment(condominio_id, skip, page_size)
    total_pages = (total + page_size - 1) // page_size
    return PaginatedReimbursementResponse(
        items=requests,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{request_id}", response_model=ReimbursementRequestResponse)
async def get_reimbursement(
    request_id: UUID,
    user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
):
    """Busca solicitação por ID."""
    service = ReimbursementService(db)
    request = await service.get_request(request_id)

    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Solicitação não encontrada",
        )

    # re-fetch com relacionamentos (o commit expira a sessão → serializar o objeto direto dava 500)
    return await service.get_request(request_id)


@router.put("/{request_id}", response_model=ReimbursementRequestResponse)
async def update_reimbursement(
    request_id: UUID,
    data: ReimbursementRequestUpdate,
    user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
):
    """Atualiza uma solicitação (apenas em rascunho)."""
    service = ReimbursementService(db)

    try:
        request = await service.update_request(request_id, data, user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Solicitação não encontrada",
        )

    # re-fetch com relacionamentos (o commit expira a sessão → serializar o objeto direto dava 500)
    return await service.get_request(request_id)


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reimbursement(
    request_id: UUID,
    user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
):
    """Exclui uma solicitação (apenas em rascunho)."""
    service = ReimbursementService(db)

    try:
        deleted = await service.delete_request(request_id, user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Solicitação não encontrada",
        )


@router.post("/{request_id}/submit", response_model=ReimbursementRequestResponse)
async def submit_reimbursement(
    request_id: UUID,
    data: ReimbursementSubmitRequest | None = None,
    user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
):
    """Submete solicitação para aprovação."""
    service = ReimbursementService(db)

    try:
        notes = data.notes if data else None
        request = await service.submit_request(request_id, user.id, notes)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Solicitação não encontrada",
        )

    # re-fetch com relacionamentos (o commit expira a sessão → serializar o objeto direto dava 500)
    return await service.get_request(request_id)


@router.post("/{request_id}/cancel", response_model=ReimbursementRequestResponse)
async def cancel_reimbursement(
    request_id: UUID,
    reason: str | None = None,
    user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
):
    """Cancela uma solicitação."""
    service = ReimbursementService(db)

    try:
        request = await service.cancel_request(request_id, user.id, reason)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Solicitação não encontrada",
        )

    # re-fetch com relacionamentos (o commit expira a sessão → serializar o objeto direto dava 500)
    return await service.get_request(request_id)


# ==================== ITENS ====================


@router.post("/{request_id}/items", response_model=ReimbursementItemResponse, status_code=status.HTTP_201_CREATED)
async def add_item(
    request_id: UUID,
    data: ReimbursementItemCreate,
    user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
):
    """Adiciona item a uma solicitação."""
    service = ReimbursementService(db)

    try:
        item = await service.add_item(request_id, data, user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Solicitação não encontrada",
        )

    return item


@router.put("/{request_id}/items/{item_id}", response_model=ReimbursementItemResponse)
async def update_item(
    request_id: UUID,
    item_id: UUID,
    data: ReimbursementItemUpdate,
    user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
):
    """Atualiza um item."""
    service = ReimbursementService(db)

    try:
        item = await service.update_item(request_id, item_id, data, user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item não encontrado",
        )

    return item


@router.delete("/{request_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    request_id: UUID,
    item_id: UUID,
    user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
):
    """Remove um item."""
    service = ReimbursementService(db)

    try:
        deleted = await service.delete_item(request_id, item_id, user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item não encontrado",
        )


# ==================== ANEXOS ====================


@router.post("/{request_id}/attachments", response_model=ReimbursementAttachmentResponse, status_code=201)
async def upload_attachment(
    request_id: UUID,
    file: UploadFile = File(...),
    item_id: UUID | None = Form(None),
    attachment_type: str = Form("outros"),
    description: str | None = Form(None),
    user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
):
    """Upload de comprovante/anexo."""
    # Validar arquivo usando service
    validator = FileValidator(
        max_size=10 * 1024 * 1024,  # 10MB
        allowed_types=[
            "image/jpeg",
            "image/png",
            "image/gif",
            "image/webp",
            "application/pdf",
        ],
    )

    content = await validator.validate_file(file)

    service = ReimbursementService(db)

    data = ReimbursementAttachmentCreate(
        item_id=item_id,
        attachment_type=attachment_type,
        description=description,
    )

    try:
        attachment = await service.add_attachment(
            request_id=request_id,
            data=data,
            file_content=content,
            original_filename=file.filename or "unknown",
            mime_type=file.content_type or "application/octet-stream",
            user_id=user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Solicitação não encontrada",
        )

    return attachment


@router.get("/{request_id}/attachments", response_model=list[ReimbursementAttachmentResponse])
async def list_attachments(
    request_id: UUID,
    item_id: UUID | None = Query(None),
    user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
):
    """Lista anexos de uma solicitação."""
    service = ReimbursementService(db)
    return await service.list_attachments(request_id, item_id)


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment(
    attachment_id: UUID,
    user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
):
    """Remove um anexo."""
    service = ReimbursementService(db)

    try:
        deleted = await service.delete_attachment(attachment_id, user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Anexo não encontrado",
        )


@router.get("/attachments/{attachment_id}/download")
async def download_attachment(
    attachment_id: UUID,
    user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
):
    """Download de anexo."""
    from fastapi.responses import FileResponse

    service = ReimbursementService(db)
    attachment = await service.get_attachment(attachment_id)

    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Anexo não encontrado",
        )

    return FileResponse(
        path=attachment.file_path,
        filename=attachment.original_name or attachment.file_name,
        media_type=attachment.mime_type,
    )


# ==================== APROVAÇÕES ====================


@router.get("/approvals/pending", response_model=PaginatedReimbursementResponse)
async def list_pending_approvals(
    user: CurrentActiveUser,
    condominio_id: CondominioId,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    approval_level: str | None = Query(None),
):
    """Lista solicitações pendentes de aprovação."""
    service = ApprovalService(db)
    skip = (page - 1) * page_size

    requests, total = await service.list_pending_approvals(condominio_id, approval_level, skip, page_size)

    total_pages = (total + page_size - 1) // page_size

    return PaginatedReimbursementResponse(
        items=requests,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("/{request_id}/analyze", response_model=ReimbursementRequestResponse)
async def start_analysis(
    request_id: UUID,
    user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
):
    """Inicia análise de uma solicitação."""
    service = ApprovalService(db)

    try:
        request = await service.start_analysis(request_id, user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Solicitação não encontrada",
        )

    # re-fetch com relacionamentos (o commit expira a sessão → serializar o objeto direto dava 500)
    return await service.get_request(request_id)


@router.post("/{request_id}/approve", response_model=ReimbursementRequestResponse)
async def approve_reimbursement(
    request_id: UUID,
    data: ReimbursementApproveRequest | None = None,
    user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
):
    """Aprova uma solicitação de reembolso."""
    service = ApprovalService(db)

    try:
        request = await service.approve_request(
            request_id=request_id,
            user_id=user.id,
            comments=data.comments if data else None,
            approved_items=data.approved_items if data else None,
            rejected_items=data.rejected_items if data else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Solicitação não encontrada",
        )

    # re-fetch com relacionamentos (o commit expira a sessão → serializar o objeto direto dava 500)
    return await service.get_request(request_id)


@router.post("/{request_id}/reject", response_model=ReimbursementRequestResponse)
async def reject_reimbursement(
    request_id: UUID,
    data: ReimbursementRejectRequest,
    user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
):
    """Rejeita uma solicitação de reembolso."""
    service = ApprovalService(db)

    try:
        request = await service.reject_request(request_id, user.id, data.reason)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Solicitação não encontrada",
        )

    # re-fetch com relacionamentos (o commit expira a sessão → serializar o objeto direto dava 500)
    return await service.get_request(request_id)


@router.post("/{request_id}/return", response_model=ReimbursementRequestResponse)
async def return_reimbursement(
    request_id: UUID,
    data: ReimbursementReturnRequest,
    user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
):
    """Devolve solicitação para rascunho."""
    service = ApprovalService(db)

    try:
        request = await service.return_to_draft(request_id, user.id, data.reason)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Solicitação não encontrada",
        )

    # re-fetch com relacionamentos (o commit expira a sessão → serializar o objeto direto dava 500)
    return await service.get_request(request_id)


# ==================== PROCESSAMENTO FINANCEIRO ====================
# (list_ready_for_payment foi movida para antes de /{request_id} — ver acima)


@router.post("/{request_id}/process", response_model=ReimbursementRequestResponse)
async def process_reimbursement(
    request_id: UUID,
    data: ReimbursementProcessRequest | None = None,
    user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Processa reembolso aprovado gerando conta a pagar.

    Requer permissão de processamento financeiro.
    """
    service = ApprovalService(db)

    try:
        request = await service.process_payment(
            request_id=request_id,
            user_id=user.id,
            due_date=data.due_date if data else None,
            notes=data.notes if data else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Solicitação não encontrada",
        )

    # re-fetch com relacionamentos (o commit expira a sessão → serializar o objeto direto dava 500)
    return await service.get_request(request_id)
