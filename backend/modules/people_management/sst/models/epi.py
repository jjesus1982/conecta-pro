"""Model de entrega de EPI."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, Date, DateTime, Integer, String, Text
from sqlalchemy.orm import declarative_base as _declarative_base

try:
    from core.database import Base
except ImportError:
    Base = _declarative_base()


class EPIDeliveryModel(Base):
    """Registro de entrega de EPI."""

    __tablename__ = "gp_epi_deliveries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    delivery_id = Column(String(36), unique=True, nullable=False, index=True)
    employee_id = Column(String(36), nullable=False, index=True)

    epi_nome = Column(String(255), nullable=False)
    epi_ca = Column(String(20), nullable=True)  # Certificado de Aprovacao
    quantidade = Column(Integer, nullable=False, default=1)
    nr = Column(String(10), nullable=False, default="NR-6")

    data_entrega = Column(Date, nullable=False)
    data_validade = Column(Date, nullable=True)
    data_devolucao = Column(Date, nullable=True)

    motivo_devolucao = Column(Text, nullable=True)
    assinatura_funcionario = Column(String(500), nullable=True)

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC).replace(tzinfo=None))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "delivery_id": self.delivery_id,
            "employee_id": self.employee_id,
            "epi": self.epi_nome,
            "ca": self.epi_ca,
            "quantidade": self.quantidade,
            "nr": self.nr,
            "data_entrega": str(self.data_entrega),
            "data_validade": str(self.data_validade) if self.data_validade else None,
        }
