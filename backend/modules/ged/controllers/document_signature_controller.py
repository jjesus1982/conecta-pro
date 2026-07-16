"""Controller para DocumentSignature."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_db
from modules.ged.models.document_signature import SignatureStatus
from modules.ged.schemas.document_signature import (
    DocumentSignatureCreate,
    DocumentSignatureResponse,
    DocumentSignatureUpdate,
    SignatureRefusalRequest,
    SignatureRequest,
    SignatureStats,
)
from modules.ged.services.document_signature_service import DocumentSignatureService


def _uid(current_user) -> str:
    """Extrai user id de User object ou dict."""
    return str(current_user.id) if hasattr(current_user, "id") else _uid(current_user)


class BulkSignatureRequest(BaseModel):
    """Request para criação de assinaturas em lote."""

    document_id: str = Field(..., description="ID do documento")
    signers: list[dict] = Field(..., description="Lista de signatários")


class SignatureRequestBody(BaseModel):
    """Request para solicitação de assinaturas."""

    document_id: str = Field(..., description="ID do documento")
    signers: list[dict] = Field(..., description="Lista de signatários")
    sequential: bool = Field(False, description="Assinar em sequência")
    deadline_days: int = Field(7, ge=1, le=90, description="Prazo em dias")
    message: str | None = Field(None, description="Mensagem para signatários")


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/document-signatures", tags=["GED - Assinaturas"])


@router.post("", response_model=DocumentSignatureResponse, status_code=status.HTTP_201_CREATED)
async def create_signature(
    data: DocumentSignatureCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> DocumentSignatureResponse:
    """Cria solicitação de assinatura."""
    service = DocumentSignatureService(db)
    try:
        data.created_by = _uid(current_user)
        return await service.create(data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.error("Erro ao criar assinatura: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao criar assinatura",
        ) from e


@router.post("/bulk", response_model=list[DocumentSignatureResponse], status_code=201)
async def create_bulk_signatures(
    data: BulkSignatureRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> list[DocumentSignatureResponse]:
    """Cria múltiplas solicitações de assinatura."""
    service = DocumentSignatureService(db)
    try:
        return await service.create_bulk(data.document_id, data.signers, _uid(current_user))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/{signature_id:uuid}", response_model=DocumentSignatureResponse)
async def get_signature(
    signature_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentSignatureResponse:
    """Busca assinatura por ID."""
    service = DocumentSignatureService(db)
    signature = await service.get_by_id(signature_id)
    if not signature:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assinatura não encontrada")
    return signature


@router.get("/token/{token}", response_model=DocumentSignatureResponse)
async def get_by_token(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> DocumentSignatureResponse:
    """Busca assinatura por token."""
    service = DocumentSignatureService(db)
    signature = await service.get_by_token(token)
    if not signature:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assinatura não encontrada")
    return signature


@router.put("/{signature_id:uuid}", response_model=DocumentSignatureResponse)
async def update_signature(
    signature_id: str,
    data: DocumentSignatureUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentSignatureResponse:
    """Atualiza assinatura."""
    service = DocumentSignatureService(db)
    signature = await service.update(signature_id, data)
    if not signature:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assinatura não encontrada")
    return signature


@router.delete("/{signature_id:uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_signature(
    signature_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> None:
    """Remove assinatura."""
    service = DocumentSignatureService(db)
    try:
        if not await service.delete(signature_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assinatura não encontrada",
            )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/document/{document_id}", response_model=list[DocumentSignatureResponse])
async def get_by_document(
    document_id: str,
    signature_status: SignatureStatus | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[DocumentSignatureResponse]:
    """Retorna assinaturas de um documento."""
    service = DocumentSignatureService(db)
    return await service.get_by_document(document_id, signature_status)


@router.get("/document/{document_id}/pending", response_model=list[DocumentSignatureResponse])
async def get_pending_by_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[DocumentSignatureResponse]:
    """Retorna assinaturas pendentes do documento."""
    service = DocumentSignatureService(db)
    return await service.get_pending_by_document(document_id)


@router.get("/signer", include_in_schema=False)
@router.get("/signer/list", response_model=list[DocumentSignatureResponse])
async def get_by_signer(
    signature_status: SignatureStatus | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> list[DocumentSignatureResponse]:
    """Retorna assinaturas do usuário."""
    service = DocumentSignatureService(db)
    return await service.get_by_signer(
        signer_id=_uid(current_user),
        status=signature_status,
    )


@router.get("/signer/pending", response_model=list[DocumentSignatureResponse])
async def get_pending_by_signer(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> list[DocumentSignatureResponse]:
    """Retorna assinaturas pendentes do usuário."""
    service = DocumentSignatureService(db)
    return await service.get_pending_by_signer(signer_id=_uid(current_user))


@router.post("/{signature_id:uuid}/sign", response_model=DocumentSignatureResponse, status_code=201)
async def sign(
    signature_id: str,
    data: SignatureRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentSignatureResponse:
    """Registra assinatura."""
    service = DocumentSignatureService(db)
    try:
        # Adiciona informações da requisição
        data.ip_address = request.client.host if request.client else None
        data.user_agent = request.headers.get("user-agent")

        signature = await service.sign(signature_id, data)
        if not signature:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assinatura não encontrada",
            )
        return signature
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{signature_id:uuid}/refuse", response_model=DocumentSignatureResponse, status_code=201)
async def refuse(
    signature_id: str,
    data: SignatureRefusalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentSignatureResponse:
    """Recusa assinatura."""
    service = DocumentSignatureService(db)
    try:
        signature = await service.refuse(signature_id, data)
        if not signature:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assinatura não encontrada",
            )
        return signature
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{signature_id:uuid}/cancel", response_model=DocumentSignatureResponse, status_code=201)
async def cancel(
    signature_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentSignatureResponse:
    """Cancela assinatura."""
    service = DocumentSignatureService(db)
    try:
        signature = await service.cancel(signature_id)
        if not signature:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assinatura não encontrada",
            )
        return signature
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{signature_id:uuid}/verify", response_model=DocumentSignatureResponse, status_code=201)
async def verify(
    signature_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentSignatureResponse:
    """Verifica assinatura."""
    service = DocumentSignatureService(db)
    try:
        signature = await service.verify(signature_id)
        if not signature:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assinatura não encontrada",
            )
        return signature
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{signature_id:uuid}/notify", response_model=DocumentSignatureResponse, status_code=201)
async def send_notification(
    signature_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentSignatureResponse:
    """Envia notificação."""
    service = DocumentSignatureService(db)
    signature = await service.send_notification(signature_id)
    if not signature:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assinatura não encontrada")
    return signature


@router.post("/{signature_id:uuid}/remind", response_model=DocumentSignatureResponse, status_code=201)
async def send_reminder(
    signature_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentSignatureResponse:
    """Envia lembrete."""
    service = DocumentSignatureService(db)
    signature = await service.send_reminder(signature_id)
    if not signature:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assinatura não encontrada")
    return signature


@router.post("/{signature_id:uuid}/regenerate-token", status_code=201)
async def regenerate_token(
    signature_id: str,
    expires_in_hours: int = Query(72, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict:
    """Regenera token de assinatura."""
    service = DocumentSignatureService(db)
    token = await service.regenerate_token(signature_id, expires_in_hours)
    if not token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assinatura não encontrada")
    return {"token": token}


@router.post("/{signature_id:uuid}/extend", response_model=DocumentSignatureResponse, status_code=201)
async def extend_deadline(
    signature_id: str,
    new_deadline: datetime = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentSignatureResponse:
    """Estende prazo de assinatura."""
    service = DocumentSignatureService(db)
    signature = await service.extend_deadline(signature_id, new_deadline)
    if not signature:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assinatura não encontrada")
    return signature


@router.post("/expire-overdue/run", status_code=201)
async def expire_overdue(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict:
    """Expira assinaturas vencidas."""
    service = DocumentSignatureService(db)
    count = await service.expire_overdue()
    return {"expired_count": count}


@router.get("/document/{document_id}/next", response_model=DocumentSignatureResponse | None)
async def get_next_in_sequence(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DocumentSignatureResponse | None:
    """Retorna próxima assinatura na sequência."""
    service = DocumentSignatureService(db)
    return await service.get_next_in_sequence(document_id)


@router.get("/document/{document_id}/fully-signed")
async def is_fully_signed(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict:
    """Verifica se documento está completamente assinado."""
    service = DocumentSignatureService(db)
    is_signed = await service.is_document_fully_signed(document_id)
    return {"is_fully_signed": is_signed}


@router.get("/stats/summary", response_model=SignatureStats)
async def get_stats(
    document_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> SignatureStats:
    """Retorna estatísticas."""
    service = DocumentSignatureService(db)
    return await service.get_stats(document_id)


@router.post("/request", response_model=list[DocumentSignatureResponse], status_code=201)
async def request_signatures(
    data: SignatureRequestBody,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> list[DocumentSignatureResponse]:
    """Solicita assinaturas para documento."""
    service = DocumentSignatureService(db)
    try:
        return await service.request_signatures(
            document_id=data.document_id,
            signers=data.signers,
            created_by=_uid(current_user),
            sequential=data.sequential,
            deadline_days=data.deadline_days,
            message=data.message,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/document/{document_id}/cancel-all", status_code=201)
async def cancel_all_pending(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict:
    """Cancela todas as assinaturas pendentes."""
    service = DocumentSignatureService(db)
    count = await service.cancel_all_pending(document_id)
    return {"cancelled_count": count}


@router.get("/{signature_id:uuid}/certificate")
async def get_certificate(
    signature_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict:
    """Retorna certificado de assinatura."""
    service = DocumentSignatureService(db)
    certificate = await service.get_signature_certificate(signature_id)
    if not certificate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assinatura não encontrada ou não realizada",
        )
    return certificate
