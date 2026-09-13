"""Conformidade de vigilante — cursos/reciclagem com validade e equipamento controlado por série (frente 05).

DDL de origem: auditoria/frentes/FRENTE_05_vigilante.md. O serviço (`services/conformidade_vigilante`)
lê e grava por SQL; estes models existem para o alembic enxergar as tabelas e para quem precisar do ORM.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base

TIPOS_CURSO = ("formacao", "reciclagem_patrimonial", "reciclagem_escolta_armada", "reciclagem_vspp", "outro")
TIPOS_EQUIPAMENTO = ("armamento", "colete")


class VigilanteCurso(Base):
    """Curso/reciclagem concluído. `vence_em` = `data_conclusao` + `validade_meses` (conta da CONCLUSÃO)."""

    __tablename__ = "vigilante_cursos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tipo: Mapped[str] = mapped_column(String(40), nullable=False)
    data_conclusao: Mapped[date] = mapped_column(Date, nullable=False)
    validade_meses: Mapped[int] = mapped_column(Integer, nullable=False)
    vence_em: Mapped[date] = mapped_column(Date, nullable=False)
    local: Mapped[str | None] = mapped_column(String(120))
    certificado_url: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EquipamentoControlado(Base):
    """Arma ou colete, UM por número de série. `status` é estado físico; posse deriva da alocação aberta."""

    __tablename__ = "equipamentos_controlados"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    numero_serie: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    modelo: Mapped[str | None] = mapped_column(String(80))
    calibre: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="ativo")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EquipamentoControladoAlocacao(Base):
    """Entrega datada a um responsável; `devolvido_em` NULL = em posse (índice único parcial no banco)."""

    __tablename__ = "equipamentos_controlados_alocacoes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    equipamento_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("equipamentos_controlados.id"), nullable=False
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False, index=True
    )
    entregue_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    devolvido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    entregue_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    devolvido_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    observacao: Mapped[str | None] = mapped_column(Text)
