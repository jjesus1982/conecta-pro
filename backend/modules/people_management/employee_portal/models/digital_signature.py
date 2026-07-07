"""
Model para assinaturas digitais do Portal do Funcionario.
"""

import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.database import Base


class DocumentType(enum.StrEnum):
    """Tipos de documento que podem ser assinados digitalmente."""

    WARNING = "warning"
    SUSPENSION = "suspension"
    PAYSLIP = "payslip"
    CONTRACT = "contract"
    VACATION = "vacation"
    POLICY = "policy"
    TRAINING_CERTIFICATE = "training_certificate"
    FICHA_EPI = "ficha_epi"  # Ficha de EPI (NR-6) — assinada pelo funcionário
    OTHER = "other"


class PortalDigitalSignature(Base):
    """Assinatura digital de documentos pelo portal.

    Armazena o hash da assinatura, metadados do dispositivo e
    informacoes de validacao/invalidacao.

    Attributes:
        id: Identificador unico.
        document_id: ID do documento assinado.
        document_type: Tipo do documento.
        employee_id: FK para o funcionario signatario.
        signature_hash: Hash SHA-256 da assinatura.
        ip_address: IP no momento da assinatura.
        user_agent: User agent do navegador.
        device_fingerprint: Fingerprint do dispositivo.
        geolocation: Dados de geolocalizacao em JSON.
        signed_at: Data/hora da assinatura.
        is_valid: Se a assinatura ainda e valida.
        invalidated_at: Data/hora da invalidacao (se houver).
        invalidation_reason: Motivo da invalidacao.
        created_at: Data/hora de criacao do registro.
    """

    __tablename__ = "portal_digital_signatures"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Documentos do portal (ged_kit_documents) usam ID UUID/texto; armazenamos
    # como String para casar com o path do controller (UUID str). Ver auditoria.
    document_id = Column(String(64), nullable=False, index=True)
    document_type = Column(
        Enum(DocumentType, name="portal_document_type_enum"),
        nullable=False,
    )
    employee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    signature_hash = Column(String(256), nullable=False, unique=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    device_fingerprint = Column(String(255), nullable=True)
    geolocation = Column(JSONB, nullable=True)
    signed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_valid = Column(Boolean, default=True, nullable=False)
    invalidated_at = Column(DateTime, nullable=True)
    invalidation_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
