"""
Model de Checkpoint de Inspecao.

Representa um ponto de verificacao durante a ronda, onde o inspetor
registra observacoes, ocorrencias e medidas disciplinares.

Author: Conecta PRO Team
Date: 2026-01-23
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base

if TYPE_CHECKING:
    from .inspection_round import InspectionRound


class CheckpointType(StrEnum):
    """Tipo de checkpoint realizado."""

    VERIFICACAO_POSTO = "verificacao_posto"
    VERIFICACAO_FUNCIONARIO = "verificacao_funcionario"
    REGISTRO_OCORRENCIA = "registro_ocorrencia"
    MEDIDA_DISCIPLINAR = "medida_disciplinar"
    OBSERVACAO_GERAL = "observacao_geral"
    FOTO_EVIDENCIA = "foto_evidencia"
    # Visita de gestão ao condomínio (check-in/out georreferenciado + atividades)
    CHECKIN_CONDOMINIO = "checkin_condominio"
    CHECKOUT_CONDOMINIO = "checkout_condominio"
    REUNIAO = "reuniao"
    ALTERACAO_OPERACIONAL = "alteracao_operacional"


class CheckpointStatus(StrEnum):
    """Status do checkpoint."""

    CONFORME = "conforme"
    NAO_CONFORME = "nao_conforme"
    PENDENTE = "pendente"
    COM_OCORRENCIA = "com_ocorrencia"


class InspectionCheckpoint(Base):
    """
    Modelo de Checkpoint de Inspecao.

    Representa um registro feito durante a ronda em um posto especifico,
    podendo ser uma verificacao de conformidade, registro de ocorrencia,
    aplicacao de medida disciplinar ou observacao geral.

    Attributes:
        id: Identificador unico UUID.
        inspection_round_id: ID da ronda pai.
        post_id: ID do posto inspecionado.
        post_name: Nome do posto (snapshot).
        checkpoint_type: Tipo de checkpoint.
        status: Status da verificacao.
        employee_id: ID do funcionario verificado (se aplicavel).
        employee_name: Nome do funcionario (snapshot).
        employee_position: Cargo do funcionario (snapshot).
        occurrence_id: ID da ocorrencia criada (se houver).
        disciplinary_action_id: ID da medida disciplinar (se houver).
        description: Descricao do checkpoint.
        observations: Observacoes adicionais.
        photos: Lista de URLs de fotos.
        latitude: Latitude do checkpoint.
        longitude: Longitude do checkpoint.
    """

    __tablename__ = "inspection_checkpoints"
    __table_args__ = (
        Index("ix_inspection_checkpoints_round", "inspection_round_id"),
        Index("ix_inspection_checkpoints_post", "post_id"),
        Index("ix_inspection_checkpoints_employee", "employee_id"),
        Index("ix_inspection_checkpoints_type", "checkpoint_type"),
    )

    # === Identificacao ===
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    inspection_round_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("inspection_rounds.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # === Posto ===
    post_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("posts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    post_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    client_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        nullable=True,
    )
    client_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # === Tipo e Status ===
    checkpoint_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=CheckpointType.VERIFICACAO_POSTO.value,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=CheckpointStatus.PENDENTE.value,
    )

    # === Funcionario (se aplicavel) ===
    employee_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        nullable=True,
        index=True,
    )
    employee_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    employee_cpf: Mapped[str | None] = mapped_column(
        String(14),
        nullable=True,
    )
    employee_position: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # === Vinculo com Ocorrencia ===
    occurrence_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        nullable=True,
    )
    occurrence_code: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    # === Vinculo com Medida Disciplinar ===
    disciplinary_action_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        nullable=True,
    )
    disciplinary_action_code: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )
    disciplinary_action_type: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    # === Descricao ===
    title: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    observations: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # === Categoria da Infracao (se nao conforme) ===
    infraction_category: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    infraction_severity: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    # === Evidencias ===
    photos: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
        default=list,
    )
    attachments: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
        default=list,
    )

    # === Geolocalizacao ===
    latitude: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    longitude: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    # === Ordem ===
    sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    # === Metadados ===
    extra_data: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
    )

    # === Controle ===
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
    )
    created_by: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        nullable=True,
    )

    # === Relacionamentos ===
    inspection_round: Mapped[InspectionRound] = relationship(
        "InspectionRound",
        back_populates="checkpoints",
    )

    def __repr__(self) -> str:
        return f"<InspectionCheckpoint {self.checkpoint_type} - {self.status}>"

    # === Properties ===

    @property
    def is_conforme(self) -> bool:
        """Verifica se o checkpoint esta conforme."""
        return self.status == CheckpointStatus.CONFORME.value

    @property
    def has_occurrence(self) -> bool:
        """Verifica se tem ocorrencia vinculada."""
        return self.occurrence_id is not None

    @property
    def has_disciplinary_action(self) -> bool:
        """Verifica se tem medida disciplinar vinculada."""
        return self.disciplinary_action_id is not None

    @property
    def checkpoint_type_display(self) -> str:
        """Retorna nome de exibicao do tipo."""
        display_names = {
            CheckpointType.VERIFICACAO_POSTO.value: "Verificacao de Posto",
            CheckpointType.VERIFICACAO_FUNCIONARIO.value: "Verificacao de Funcionario",
            CheckpointType.REGISTRO_OCORRENCIA.value: "Registro de Ocorrencia",
            CheckpointType.MEDIDA_DISCIPLINAR.value: "Medida Disciplinar",
            CheckpointType.OBSERVACAO_GERAL.value: "Observacao Geral",
            CheckpointType.FOTO_EVIDENCIA.value: "Foto/Evidencia",
        }
        return display_names.get(self.checkpoint_type, self.checkpoint_type)

    @property
    def status_display(self) -> str:
        """Retorna nome de exibicao do status."""
        display_names = {
            CheckpointStatus.CONFORME.value: "Conforme",
            CheckpointStatus.NAO_CONFORME.value: "Nao Conforme",
            CheckpointStatus.PENDENTE.value: "Pendente",
            CheckpointStatus.COM_OCORRENCIA.value: "Com Ocorrencia",
        }
        return display_names.get(self.status, self.status)

    # === Methods ===

    def mark_conforme(self, observations: str | None = None) -> None:
        """Marca checkpoint como conforme."""
        self.status = CheckpointStatus.CONFORME.value
        if observations:
            self.observations = observations

    def mark_nao_conforme(
        self,
        description: str,
        infraction_category: str | None = None,
        infraction_severity: str | None = None,
    ) -> None:
        """Marca checkpoint como nao conforme."""
        self.status = CheckpointStatus.NAO_CONFORME.value
        self.description = description
        if infraction_category:
            self.infraction_category = infraction_category
        if infraction_severity:
            self.infraction_severity = infraction_severity

    def link_occurrence(self, occurrence_id: str, occurrence_code: str) -> None:
        """Vincula uma ocorrencia ao checkpoint."""
        self.occurrence_id = occurrence_id
        self.occurrence_code = occurrence_code
        self.status = CheckpointStatus.COM_OCORRENCIA.value

    def link_disciplinary_action(
        self,
        action_id: str,
        action_code: str,
        action_type: str,
    ) -> None:
        """Vincula uma medida disciplinar ao checkpoint."""
        self.disciplinary_action_id = action_id
        self.disciplinary_action_code = action_code
        self.disciplinary_action_type = action_type

    def add_photo(self, photo_url: str, description: str | None = None) -> None:
        """Adiciona foto ao checkpoint."""
        if self.photos is None:
            self.photos = []
        self.photos.append(
            {
                "url": photo_url,
                "description": description,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    def set_employee(
        self,
        employee_id: str,
        employee_name: str,
        employee_cpf: str | None = None,
        employee_position: str | None = None,
    ) -> None:
        """Define o funcionario do checkpoint."""
        self.employee_id = employee_id
        self.employee_name = employee_name
        if employee_cpf:
            self.employee_cpf = employee_cpf
        if employee_position:
            self.employee_position = employee_position

    def set_location(self, latitude: float, longitude: float) -> None:
        """Define a localizacao do checkpoint."""
        self.latitude = latitude
        self.longitude = longitude
