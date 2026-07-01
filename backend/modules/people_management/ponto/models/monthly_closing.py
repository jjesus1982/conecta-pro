"""Model de fechamento mensal de ponto."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
)

try:
    from core.database import Base
except ImportError:  # pragma: no cover
    from sqlalchemy.orm import declarative_base

    Base = declarative_base()


class MonthlyClosingModel(Base):
    """Fechamento mensal de ponto de um funcionario."""

    __tablename__ = "gp_monthly_closings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # [Ponto loop] era Integer — employees têm UUID (String 36), como clock_punch/justification
    employee_id = Column(String(36), nullable=False, index=True)
    month = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)

    # Totais
    total_horas_trabalhadas = Column(Float, nullable=False, default=0.0)
    total_horas_extras_50 = Column(Float, nullable=False, default=0.0)
    total_horas_extras_100 = Column(Float, nullable=False, default=0.0)
    total_horas_noturnas = Column(Float, nullable=False, default=0.0)
    total_faltas = Column(Integer, nullable=False, default=0)
    total_atrasos_minutos = Column(Float, nullable=False, default=0.0)
    total_dias_trabalhados = Column(Integer, nullable=False, default=0)

    # Status
    fechado = Column(Boolean, nullable=False, default=False)
    fechado_por = Column(String(36), nullable=True)
    fechado_em = Column(DateTime, nullable=True)

    # Observacoes
    observacoes = Column(Text, nullable=True)

    # Auditoria
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "month": self.month,
            "year": self.year,
            "total_horas_trabalhadas": self.total_horas_trabalhadas,
            "total_horas_extras_50": self.total_horas_extras_50,
            "total_horas_extras_100": self.total_horas_extras_100,
            "total_horas_noturnas": self.total_horas_noturnas,
            "total_faltas": self.total_faltas,
            "total_atrasos_minutos": self.total_atrasos_minutos,
            "total_dias_trabalhados": self.total_dias_trabalhados,
            "fechado": self.fechado,
            "fechado_em": self.fechado_em.isoformat() if self.fechado_em else None,
        }
