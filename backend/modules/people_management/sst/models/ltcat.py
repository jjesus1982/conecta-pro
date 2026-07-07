"""Model do LTCAT — Laudo Técnico das Condições Ambientais de Trabalho.

Fonte REAL do endpoint /sst/ltcat/status (fim do status hardcoded).
Lei 8.213/91 Art. 58 + IN INSS 128/2022. Enquanto o laudo não for elaborado
por engenheiro de segurança, o status honesto é 'pendente_elaboracao'.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Column, Date, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID

from core.database import Base


class LTCATModel(Base):
    """Registro do LTCAT vigente/pendente."""

    __tablename__ = "sst_ltcat"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    status = Column(String(30), nullable=False, default="pendente_elaboracao")
    # pendente_elaboracao|em_elaboracao|vigente|vencido

    responsavel_tecnico = Column(String(200), nullable=True)
    registro_conselho = Column(String(60), nullable=True)  # CREA/CRM etc.
    validade_inicio = Column(Date, nullable=True)
    validade_fim = Column(Date, nullable=True)
    observacoes = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "status": self.status,
            "responsavel_tecnico": self.responsavel_tecnico,
            "registro_conselho": self.registro_conselho,
            "validade_inicio": str(self.validade_inicio) if self.validade_inicio else None,
            "validade_fim": str(self.validade_fim) if self.validade_fim else None,
            "observacoes": self.observacoes,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
