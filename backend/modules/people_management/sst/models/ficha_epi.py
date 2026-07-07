"""Model da Ficha de EPI digital (NR-6 / NR-1).

Uma ficha cobre uma ou mais entregas de EPI (gp_epi_deliveries) de um mesmo
funcionário. O PDF padrão-ouro é gerado a partir do SNAPSHOT em `itens`
(imutável após criação) e a assinatura é DIGITAL, pela infra do Portal do
Funcionário (portal_digital_signatures, document_type='ficha_epi').
Status honesto: pendente_assinatura|assinada — nunca "assinada" sem hash real.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.database import Base


class FichaEPIModel(Base):
    """Ficha de EPI assinável digitalmente pelo funcionário."""

    __tablename__ = "sst_fichas_epi"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    employee_id = Column(UUID(as_uuid=False), nullable=False, index=True)
    employee_nome = Column(String(200), nullable=True)

    # Snapshot imutável do que foi entregue (fonte: gp_epi_deliveries no momento da geração)
    delivery_ids = Column(JSONB, nullable=False, default=list)
    itens = Column(JSONB, nullable=False, default=list)
    # itens: [{delivery_id, epi_nome, ca, quantidade, data_entrega, data_validade}]

    status = Column(String(30), nullable=False, default="pendente_assinatura")
    # pendente_assinatura|assinada

    # Assinatura REAL (portal_digital_signatures) — nunca fabricada
    assinatura_hash = Column(String(256), nullable=True)
    assinado_em = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ficha_id": str(self.id),
            "employee_id": str(self.employee_id),
            "employee_nome": self.employee_nome,
            "delivery_ids": self.delivery_ids or [],
            "itens": self.itens or [],
            "status": self.status,
            "assinatura_hash": self.assinatura_hash,
            "assinado_em": self.assinado_em.isoformat() if self.assinado_em else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
