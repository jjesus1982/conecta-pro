"""Model de ASO (Atestado de Saude Ocupacional)."""

import enum
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Column, Date, DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import declarative_base as _declarative_base

try:
    from core.database import Base
except ImportError:
    Base = _declarative_base()


class ASOType(enum.StrEnum):
    ADMISSIONAL = "admissional"
    PERIODICO = "periodico"
    DEMISSIONAL = "demissional"
    RETORNO_TRABALHO = "retorno_trabalho"
    MUDANCA_FUNCAO = "mudanca_funcao"


class ASOStatus(enum.StrEnum):
    AGENDADO = "agendado"
    REALIZADO = "realizado"
    CANCELADO = "cancelado"
    VENCIDO = "vencido"


class ASOModel(Base):
    """Atestado de Saude Ocupacional."""

    __tablename__ = "gp_asos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    aso_id = Column(String(36), unique=True, nullable=False, index=True)
    employee_id = Column(String(36), nullable=False, index=True)

    tipo = Column(Enum(ASOType, values_callable=lambda x: [e.value for e in x], name="aso_type_enum"), nullable=False)
    status = Column(
        Enum(ASOStatus, values_callable=lambda x: [e.value for e in x], name="aso_status_enum"),
        nullable=False,
        default=ASOStatus.AGENDADO,
    )

    data_agendamento = Column(Date, nullable=True)
    data_realizacao = Column(Date, nullable=True)
    data_validade = Column(Date, nullable=True)

    clinica = Column(String(255), nullable=True)
    medico = Column(String(255), nullable=True)
    crm = Column(String(20), nullable=True)

    apto = Column(Boolean, nullable=True)
    restricoes = Column(JSON, nullable=True, default=list)
    observacoes = Column(Text, nullable=True)

    documento_url = Column(String(500), nullable=True)

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC).replace(tzinfo=None))
    updated_at = Column(DateTime, nullable=True, onupdate=lambda: datetime.now(UTC).replace(tzinfo=None))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "aso_id": self.aso_id,
            "employee_id": self.employee_id,
            "tipo": self.tipo.value,
            "status": self.status.value,
            "data_agendamento": str(self.data_agendamento) if self.data_agendamento else None,
            "data_realizacao": str(self.data_realizacao) if self.data_realizacao else None,
            "apto": self.apto,
            "restricoes": self.restricoes,
            "clinica": self.clinica,
            "medico": self.medico,
        }
