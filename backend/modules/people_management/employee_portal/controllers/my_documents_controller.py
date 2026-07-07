"""
My Documents Controller — Documentos e assinatura digital.

Endpoints:
- GET /portal/my-documents
- POST /portal/my-documents/{id}/sign
- GET /portal/my-documents/{id}/verify-signature
"""

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.people_management.employee_portal.auth import CurrentEmployeeId
from modules.people_management.employee_portal.publishers import (
    publish_documento_assinado,
)
from modules.people_management.employee_portal.schemas.signature import (
    SignDocumentRequest,
    SignDocumentResponse,
    VerifySignatureResponse,
)
from modules.people_management.employee_portal.services.document_view_service import (
    DocumentViewService,
)
from modules.people_management.employee_portal.services.signature_service import (
    SignatureService,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Portal - Documentos"])


@router.get(
    "/my-documents",
    summary="Meus documentos",
    description="Retorna lista de documentos do funcionario com status de assinatura.",
)
async def get_my_documents(
    employee_id: CurrentEmployeeId,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna documentos do funcionario autenticado."""
    service = DocumentViewService(db)
    documents = await service.get_my_documents(employee_id=employee_id)
    return documents


@router.post(
    "/my-documents/{id}/sign",
    response_model=SignDocumentResponse,
    summary="Assinar documento",
    description="Assina um documento digitalmente usando SHA-256.",
    status_code=201,
)
async def sign_document(
    request: Request,
    employee_id: CurrentEmployeeId,
    document_id: str = Path(..., description="ID do documento (UUID)", alias="id"),
    sign_data: SignDocumentRequest = None,  # type: ignore[assignment]
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Assina um documento digitalmente com JWT do funcionario."""
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    document_type = sign_data.document_type if sign_data else "other"

    service = SignatureService(db)

    try:
        result = await service.sign_document(
            document_id=document_id,
            document_type=document_type,
            employee_id=employee_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        # Publicar evento no Event Bus (fire-and-forget)
        asyncio.create_task(
            publish_documento_assinado(
                employee_id=str(employee_id),
                funcionario_nome="",  # corrigido: 'current_user' não existe neste escopo (auth por employee_id)
                document_id=document_id,
                document_type=document_type,
            )
        )
        return SignDocumentResponse(**result)

    except ValueError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/my-documents/{id}/verify-signature",
    response_model=VerifySignatureResponse,
    summary="Verificar assinatura",
    description="Verifica a validade da assinatura de um documento.",
)
async def verify_document_signature(
    employee_id: CurrentEmployeeId,
    document_id: str = Path(..., description="ID do documento (UUID)", alias="id"),
    signature_hash: str = None,  # type: ignore[assignment]
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Verifica a assinatura digital de um documento (auth do funcionário via portal)."""
    if not signature_hash:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Hash da assinatura e obrigatorio (query param: signature_hash).",
        )

    service = SignatureService(db)
    result = await service.verify_signature(signature_hash=signature_hash)

    return VerifySignatureResponse(**result)
