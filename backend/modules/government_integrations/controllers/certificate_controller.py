"""
Module: Certificate Controller
Description: Endpoints REST para gerenciamento de certificados digitais A1
Author: Conecta PRO Team
Date: 2026-01-15
Quality Score Target: 99+/100
"""

import logging
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from modules.government_integrations.core.certificate_manager import (
    CertificateStore,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/certificates", tags=["Certificates"])


# =============================================================================
# Schemas
# =============================================================================


class CertificateUploadResponse(BaseModel):
    """Resposta do upload de certificado."""

    success: bool
    certificate_id: str
    subject: str
    issuer: str
    cpf_cnpj: str | None
    valid_from: datetime
    valid_until: datetime
    days_until_expiry: int
    type: str
    message: str


class CertificateInfoResponse(BaseModel):
    """Informacoes do certificado."""

    certificate_id: str
    subject_cn: str
    issuer_cn: str
    cpf_cnpj: str | None
    serial_number: str
    valid_from: datetime
    valid_until: datetime
    days_until_expiry: int
    is_valid: bool
    status: str
    type: str


class CertificateListResponse(BaseModel):
    """Lista de certificados."""

    total: int
    certificates: list[CertificateInfoResponse]


class CertificateValidationResponse(BaseModel):
    """Resultado da validacao do certificado."""

    is_valid: bool
    message: str
    subject: str | None
    cpf_cnpj: str | None
    valid_until: datetime | None
    days_until_expiry: int | None
    warnings: list[str]


class CertificateDeleteResponse(BaseModel):
    """Resposta de exclusao de certificado."""

    success: bool
    message: str


# =============================================================================
# Certificate Store Instance
# =============================================================================

# Instancia global do store de certificados
_certificate_store: CertificateStore | None = None


def get_certificate_store() -> CertificateStore:
    """Retorna instancia do CertificateStore."""
    global _certificate_store
    if _certificate_store is None:
        _certificate_store = CertificateStore()
    return _certificate_store


# =============================================================================
# Endpoints
# =============================================================================


