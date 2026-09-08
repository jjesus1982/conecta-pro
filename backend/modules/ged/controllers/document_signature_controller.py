"""Controller para DocumentSignature."""

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field



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


