"""
Modelo Occurrence (Ocorrência) para Operações.
"""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base

if TYPE_CHECKING:
    from modules.operacional.models import Post


class OccurrenceType(StrEnum):
    """Tipo de não conformidade/infração encontrada em fiscalização."""

    ABANDONO_POSTO = "abandono_posto"
    FALTA_UNIFORME = "falta_uniforme"
    FALTA_EPI = "falta_epi"
    DORMINDO_SERVICO = "dormindo_servico"
    USO_CELULAR = "uso_celular"
    FALTA_LIMPEZA = "falta_limpeza"
    POSTURA_INADEQUADA = "postura_inadequada"
    ATRASO = "atraso"
    FALTA_INJUSTIFICADA = "falta_injustificada"
    NAO_CONFORMIDADE_DOCUMENTAL = "nao_conformidade_documental"
    EMBRIAGUEZ = "embriaguez"
    DESRESPEITO = "desrespeito"
    NEGLIGENCIA = "negligencia"
    INSUBORDINACAO = "insubordinacao"
    # Tipos de ocorrência rápida de campo (coluna é String — aditivo, sem migration)
    INCIDENTE = "incidente"
    MANUTENCAO = "manutencao"
    CONFLITO = "conflito"
    ELOGIO = "elogio"
    OUTROS = "outros"


class OccurrenceSeverity(StrEnum):
    """Nível de severidade da infração (para ação disciplinar)."""

    LEVE = "leve"  # Advertência verbal
    MODERADA = "moderada"  # Advertência escrita
    GRAVE = "grave"  # Suspensão
    GRAVISSIMA = "gravissima"  # Demissão por justa causa


class OccurrenceCategory(StrEnum):
    """Categoria da infração."""

    DISCIPLINAR = "disciplinar"
    OPERACIONAL = "operacional"
    SEGURANCA_TRABALHO = "seguranca_trabalho"
    CONDUTA = "conduta"
    ASSIDUIDADE = "assiduidade"
    OUTROS = "outros"


class OccurrenceStatus(StrEnum):
    """Status da ocorrência."""

    ABERTA = "aberta"
    EM_ANALISE = "em_analise"
    RESOLVIDA = "resolvida"
    ARQUIVADA = "arquivada"
    CANCELADA = "cancelada"


class Occurrence(Base):
    """
    Modelo de Ocorrência Disciplinar/Fiscalização.

    Representa registros de não conformidades encontradas por SUPERVISORES/GESTORES
    durante rondas e fiscalizações nos postos de trabalho.

    Este é um registro DISCIPLINAR usado para:
    - Histórico de infrações do funcionário
    - Base para ações corretivas
    - Controle de qualidade operacional
    - Evidências para processos disciplinares

    Attributes:
        id: Identificador único
        code: Código da ocorrência (OCO-2026-00001)
        title: Título resumido da infração
        description: Descrição detalhada do que foi encontrado
        occurrence_type: Tipo da infração (abandono posto, falta uniforme, etc)
        severity: Nível de severidade (leve, moderada, grave, gravíssima)
        category: Categoria da infração
        status: Status da ocorrência
        employee_id: Funcionário envolvido (employees.id — OPCIONAL)
        inspector_id: Gestor/supervisor que fiscalizou (OBRIGATÓRIO)
        post_id: Posto onde ocorreu (OBRIGATÓRIO)
        patrol_round_id: Ronda de fiscalização relacionada (opcional)
        occurred_at: Data/hora em que foi identificada
        reported_at: Data/hora do registro
        resolved_at: Data/hora da resolução
        corrective_action: Ação corretiva aplicada (advertência, suspensão, etc)
        resolution_notes: Notas sobre a resolução
        resolved_by_id: Gestor que resolveu
        attachments: Fotos/vídeos como evidência
        witnesses: Testemunhas (texto livre)
    """

    __tablename__ = "occurrences"
    __table_args__ = {"extend_existing": True}

    # Identificação
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)

    # Informações básicas
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Classificação
    occurrence_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Status
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=OccurrenceStatus.ABERTA.value, index=True)

    # Envolvidos
    # NOTA (2026-07-07): no BANCO a FK de employee_id aponta para EMPLOYEES
    # (não users) — a anotação antiga ForeignKey("users.id") estava ERRADA.
    # Opcional: ocorrência sem funcionário específico é válida (ex.: manutenção).
    employee_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="Funcionário envolvido na ocorrência (employees.id)",
    )
    inspector_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Gestor/supervisor que fiscalizou",
    )

    # Localização (OBRIGATÓRIO)
    post_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("posts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Posto onde ocorreu a infração",
    )

    # Ronda relacionada (OPCIONAL)
    patrol_round_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        nullable=True,
        index=True,
        comment="Ronda de fiscalização relacionada",
    )

    # Testemunhas
    witnesses: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Testemunhas da infração")

    # Datas
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    reported_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Resolução e Ação Corretiva
    corrective_action: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Ação corretiva aplicada (advertência verbal, escrita, suspensão, etc)",
    )
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Evidências (fotos/vídeos)
    attachments: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Fotos/vídeos como evidência da infração",
    )

    # Controle
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)

    # Relacionamentos
    post: Mapped["Post"] = relationship("Post", back_populates="occurrences", lazy="joined")

    def __repr__(self) -> str:
        return f"<Occurrence {self.code} - {self.title}>"

    @property
    def is_resolved(self) -> bool:
        """Verifica se a ocorrência está resolvida."""
        return self.status in [OccurrenceStatus.RESOLVIDA.value, OccurrenceStatus.ARQUIVADA.value]

    @property
    def is_severe(self) -> bool:
        """Verifica se é infração grave ou gravíssima."""
        return self.severity in [OccurrenceSeverity.GRAVE.value, OccurrenceSeverity.GRAVISSIMA.value]

    @property
    def resolution_time_hours(self) -> float | None:
        """Calcula tempo de resolução em horas."""
        if self.resolved_at and self.reported_at:
            delta = self.resolved_at - self.reported_at
            return delta.total_seconds() / 3600
        return None
