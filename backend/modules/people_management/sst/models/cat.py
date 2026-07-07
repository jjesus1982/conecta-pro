"""Model de CAT (Comunicacao de Acidente de Trabalho)."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column, Date, DateTime, Integer, String, Text
from sqlalchemy.orm import declarative_base as _declarative_base

try:
    from core.database import Base
except ImportError:
    Base = _declarative_base()


class CATModel(Base):
    """Comunicacao de Acidente de Trabalho."""

    __tablename__ = "gp_cats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cat_id = Column(String(36), unique=True, nullable=False, index=True)
    employee_id = Column(String(36), nullable=False, index=True)

    tipo_acidente = Column(String(50), nullable=False)  # tipico, trajeto, doenca
    data_acidente = Column(Date, nullable=False)
    hora_acidente = Column(String(5), nullable=True)
    local = Column(String(255), nullable=False)
    descricao = Column(Text, nullable=False)
    gravidade = Column(String(20), nullable=False, default="leve")

    parte_corpo = Column(String(100), nullable=True)
    agente_causador = Column(String(255), nullable=True)
    testemunhas = Column(JSON, nullable=True, default=list)

    afastamento = Column(Integer, nullable=True, default=0)  # dias
    numero_cat_inss = Column(String(20), nullable=True)

    # eSocial S-2210 (transmissão real)
    numero_recibo_esocial = Column(String(60), nullable=True)
    esocial_status = Column(String(20), nullable=False, default="nao_transmitida")
    # nao_transmitida|transmitida|aceita|rejeitada|erro
    esocial_transmitida_em = Column(DateTime(timezone=True), nullable=True)
    esocial_protocolo = Column(String(100), nullable=True)  # protocolo REAL do lote (pull de recibos)

    # Ciclo de vida da CAT: aberta|transmitida|registrada_inss|encerrada
    status = Column(String(20), nullable=False, default="aberta")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC).replace(tzinfo=None))
    updated_at = Column(DateTime, nullable=True, onupdate=lambda: datetime.now(UTC).replace(tzinfo=None))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "cat_id": self.cat_id,
            "employee_id": self.employee_id,
            "tipo": self.tipo_acidente,
            "data": str(self.data_acidente),
            "local": self.local,
            "descricao": self.descricao,
            "gravidade": self.gravidade,
            "status": self.status,
            "afastamento_dias": self.afastamento,
        }
