"""Schemas Pydantic do módulo de assinatura universal."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


class SignerSchema(BaseModel):
    """Um signatário exigido numa solicitação."""

    signer_type: str = Field(..., description="employee | company | customer")
    signer_name: str = Field(..., description="Nome do signatário")
    signer_id: uuid.UUID | None = Field(
        None, description="UUID do funcionário/admin (opcional p/ cliente)"
    )
    signer_email: str | None = None
    signer_phone: str | None = None
    signer_document: str | None = Field(None, description="CPF/CNPJ")
    order: int = Field(1, ge=1, description="Ordem no fluxo multi-assinatura")


class CreateSignatureRequestSchema(BaseModel):
    """Payload para criar uma solicitação de assinatura."""

    document_type: str = Field(..., description="Tipo do documento (livre)")
    document_id: str = Field(..., description="ID do documento (UUID ou texto)")
    title: str = Field(..., description="Título humano da solicitação")
    signers: list[SignerSchema] = Field(..., min_length=1)
    document_name: str | None = None
    document_path: str | None = None
    document_hash: str | None = Field(None, description="SHA-256 do PDF (recomendado)")
    purpose: str = "signature"
    expires_in_days: int | None = 30
    reference_code: str | None = None
    metadata: dict[str, Any] | None = None


class EvidenceSchema(BaseModel):
    """Evidências opcionais informadas no corpo (além das capturadas do Request)."""

    device: str | None = None
    location: dict[str, Any] | None = None
    extra: dict[str, Any] | None = None


class SignRequestSchema(BaseModel):
    """Payload para assinar (funcionário/empresa autenticado)."""

    signer_name: str | None = None
    signer_document: str | None = None
    evidence: EvidenceSchema | None = None


class AssinarLoteSchema(BaseModel):
    """Payload para assinar VÁRIAS solicitações do próprio funcionário de uma vez."""

    request_ids: list[uuid.UUID] = Field(
        ..., min_length=1, max_length=50,
        description="IDs das solicitações a assinar (1..50 por chamada).",
    )
    evidence: EvidenceSchema | None = None


class PublicSignSchema(BaseModel):
    """Payload para assinatura pública de cliente (via link)."""

    access_code: str | None = Field(None, description="PIN de 6 dígitos")
    signer_name: str | None = None
    signer_document: str | None = None
    evidence: EvidenceSchema | None = None


class VerifyResponseSchema(BaseModel):
    """Resposta da verificação de hash."""

    is_valid: bool
    signature_hash: str
    signer_type: str | None = None
    signer_name: str | None = None
    document_type: str | None = None
    document_id: str | None = None
    signed_at: str | None = None
    reason: str | None = None
