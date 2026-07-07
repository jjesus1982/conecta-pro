"""
Schemas para assinatura digital de documentos.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SignDocumentRequest(BaseModel):
    """Request para assinar um documento digitalmente.

    Attributes:
        document_id: ID do documento a ser assinado.
        document_type: Tipo do documento (warning, payslip, contract, etc.).
    """

    # Documentos do portal (ged_kit_documents) usam ID UUID (str). O path param
    # é a fonte da verdade; este campo do body é opcional/informativo.
    document_id: str | None = Field(
        None, description="ID do documento (UUID). O path param prevalece."
    )
    document_type: str = Field(
        default="other",
        description="Tipo do documento (warning, suspension, payslip, contract, "
        "vacation, policy, training_certificate, other)",
    )

    model_config = ConfigDict(from_attributes=True)


class SignDocumentResponse(BaseModel):
    """Response apos assinatura bem-sucedida.

    Attributes:
        signature_hash: Hash SHA-256 gerado para a assinatura.
        signed_at: Data/hora da assinatura.
    """

    signature_hash: str
    signed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VerifySignatureRequest(BaseModel):
    """Request para verificar validade de uma assinatura.

    Attributes:
        signature_hash: Hash da assinatura a verificar.
    """

    signature_hash: str = Field(..., min_length=64, max_length=256, description="Hash da assinatura")

    model_config = ConfigDict(from_attributes=True)


class VerifySignatureResponse(BaseModel):
    """Response da verificacao de assinatura.

    Attributes:
        is_valid: Se a assinatura e valida.
        document_id: ID do documento assinado.
        document_type: Tipo do documento.
        employee_id: UUID do signatario.
        signed_at: Data/hora da assinatura.
        invalidated_at: Data/hora da invalidacao (se invalida).
        invalidation_reason: Motivo da invalidacao (se invalida).
    """

    is_valid: bool
    document_id: str | None = None
    document_type: str | None = None
    employee_id: str | None = None
    signed_at: datetime | None = None
    invalidated_at: datetime | None = None
    invalidation_reason: str | None = None

    model_config = ConfigDict(from_attributes=True)
