"""Model de Afastamento — SST."""

from datetime import date, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class TipoAfastamento(StrEnum):
    """Tipo de afastamento."""

    DOENCA = "doenca"
    ACIDENTE_TRABALHO = "acidente_trabalho"
    ACIDENTE_TRAJETO = "acidente_trajeto"
    LICENCA_MATERNIDADE = "licenca_maternidade"
    LICENCA_PATERNIDADE = "licenca_paternidade"
    OUTRO = "outro"


class StatusAfastamento(StrEnum):
    """Status do afastamento."""

    ATIVO = "ativo"
    ENCERRADO = "encerrado"
    PRORROGADO = "prorrogado"


class Afastamento(Base):
    """Registro de afastamento de colaborador."""

    __tablename__ = "sst_afastamentos"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    employee_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    employee_nome: Mapped[str] = mapped_column(String(200), nullable=False)
    employee_cargo: Mapped[str | None] = mapped_column(String(200))

    tipo: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    motivo: Mapped[str | None] = mapped_column(Text)
    data_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    data_fim_prevista: Mapped[date | None] = mapped_column(Date)
    data_retorno: Mapped[date | None] = mapped_column(Date)
    dias_previstos: Mapped[int | None] = mapped_column(Integer)

    atestado: Mapped[bool] = mapped_column(Boolean, default=True)
    cid: Mapped[str | None] = mapped_column(String(10))
    medico: Mapped[str | None] = mapped_column(String(200))
    crm: Mapped[str | None] = mapped_column(String(20))

    status: Mapped[str] = mapped_column(String(20), default=StatusAfastamento.ATIVO, index=True)

    # CCT: Ajuda medicamento R$ 300/mes
    ajuda_medicamento_ativa: Mapped[bool] = mapped_column(Boolean, default=False)
    ajuda_medicamento_valor: Mapped[float | None] = mapped_column(Numeric(10, 2))

    # CCT: Estabilidade 12 meses pos-acidente
    gera_estabilidade: Mapped[bool] = mapped_column(Boolean, default=False)
    estabilidade_ate: Mapped[date | None] = mapped_column(Date)

    # eSocial S-2230 (transmissão real)
    recibo_s2230: Mapped[str | None] = mapped_column(String(60))
    esocial_status: Mapped[str] = mapped_column(String(20), default="nao_transmitida")
    # nao_transmitida|transmitida|aceita|rejeitada|erro

    observacoes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Afastamento employee={self.employee_nome} tipo={self.tipo} status={self.status}>"
