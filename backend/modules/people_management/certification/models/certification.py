"""Model de Certificacao Humana — o gate C rastreavel dos calculos de risco juridico."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.models import Base


class CertificationStatus(StrEnum):
    """Estado da certificacao."""

    PENDENTE = "pendente"
    CERTIFICADO = "certificado"
    REJEITADO = "rejeitado"


class HRCertification(Base):  # pylint: disable=too-few-public-methods
    """Certificacao humana rastreavel de um calculo (folha/rescisao/eSocial).

    O `hash_conteudo` torna a certificacao inforjavel no tempo: certifica-se um
    conteudo especifico; se o calculo muda depois, o hash muda e a certificacao
    EXPIRA (volta a pendente). Mata o "certifiquei mes passado, mudei o codigo,
    continua verde". Nada de risco juridico vai a producao/transmissao sem uma
    linha status='certificado' aqui, com hash igual ao conteudo atual.
    """

    __tablename__ = "hr_certifications"

    id = Column(UUID(as_uuid=False), primary_key=True)

    # O QUE se certifica
    tipo_calculo = Column(String(40), nullable=False, index=True)  # folha_mensal|rescisao|esocial_s2210|...
    referencia_id = Column(String(64), nullable=True, index=True)  # id do holerite/rescisao/evento
    referencia_tipo = Column(String(40), nullable=True)
    competencia = Column(String(7), nullable=True, index=True)  # YYYY-MM
    employee_id = Column(UUID(as_uuid=False), nullable=True, index=True)
    cliente_id = Column(UUID(as_uuid=False), nullable=True, index=True)

    # Os valores (calculado pelo sistema vs golden set Dominio)
    calculado_valor = Column(Numeric(14, 2), nullable=True)
    esperado_valor = Column(Numeric(14, 2), nullable=True)  # golden set Dominio, se houver
    divergencia = Column(Boolean, default=False, nullable=False)
    divergencia_desc = Column(Text, nullable=True)
    payload = Column(JSONB, nullable=True)  # detalhamento certificado (proventos/descontos)

    # A alma anti-teatro
    hash_conteudo = Column(String(64), nullable=False, index=True)  # sha256 do conteudo certificado

    # A assinatura rastreavel
    status = Column(String(20), default=CertificationStatus.PENDENTE.value, nullable=False, index=True)
    certificado_por = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    certificado_em = Column(DateTime, nullable=True)
    observacao = Column(Text, nullable=True)

    # Controle
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
