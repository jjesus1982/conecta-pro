"""
Schemas Pydantic para Occurrence (Ocorrência).
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from modules.operacional.occurrences.models import (
    OccurrenceCategory,
    OccurrenceSeverity,
    OccurrenceStatus,
    OccurrenceType,
)


class AttachmentSchema(BaseModel):
    """Schema para anexo."""

    type: str = Field(..., description="Tipo do arquivo (image, video, document)")
    url: str = Field(..., description="URL do arquivo")
    name: str = Field(..., description="Nome do arquivo")
    size: int | None = Field(None, description="Tamanho em bytes")
    uploaded_at: datetime | None = Field(None, description="Data do upload")


class OccurrenceBase(BaseModel):
    """Schema base para Occurrence (registro disciplinar)."""

    title: str = Field(..., min_length=2, max_length=255, description="Título da infração")
    description: str = Field(..., min_length=10, description="Descrição do que foi encontrado")
    occurrence_type: OccurrenceType = Field(..., description="Tipo da infração")
    severity: OccurrenceSeverity = Field(..., description="Severidade (leve, moderada, grave, gravíssima)")
    category: OccurrenceCategory = Field(..., description="Categoria da infração")
    # Opcional p/ form rápido mobile: ausente → controller usa now()
    occurred_at: datetime | None = Field(None, description="Data/hora em que foi identificada (default: agora)")

    # Envolvidos
    # employee_id OPCIONAL: ocorrência sem funcionário específico é válida (ex.: manutenção)
    employee_id: str | None = Field(None, description="ID do funcionário envolvido (employees.id)")
    # post_id: se ausente e o líder tem exatamente 1 posto, o controller preenche automaticamente
    post_id: str | None = Field(None, description="ID do posto onde ocorreu")

    # Opcionais
    patrol_round_id: str | None = Field(None, description="ID da ronda relacionada")
    witnesses: str | None = Field(None, description="Testemunhas da infração")


class OccurrenceCreate(OccurrenceBase):
    """
    Schema para criação de Occurrence (Ocorrência Disciplinar).

    Registra infrações encontradas durante fiscalização/rondas.
    Pode gerar processos disciplinares posteriormente.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Uso de celular em horário de trabalho",
                "description": "Funcionário flagrado usando celular pessoal na portaria durante expediente, sem autorização",
                "occurrence_type": "uso_celular",
                "severity": "leve",
                "category": "conduta",
                "occurred_at": "2026-03-15T14:30:00",
                "employee_id": "550e8400-e29b-41d4-a716-446655440001",
                "post_id": "550e8400-e29b-41d4-a716-446655440002",
                "witnesses": "Supervisor João Silva",
            }
        }
    )


class OccurrenceUpdate(BaseModel):
    """
    Schema para atualização parcial de Occurrence.

    Todos os campos são opcionais. Apenas os campos fornecidos serão atualizados.
    """

    title: str | None = Field(None, min_length=2, max_length=255, description="Título da infração")
    description: str | None = Field(None, min_length=10, description="Descrição do que foi encontrado")
    occurrence_type: OccurrenceType | None = Field(None, description="Tipo da infração")
    severity: OccurrenceSeverity | None = Field(None, description="Severidade")
    category: OccurrenceCategory | None = Field(None, description="Categoria da infração")
    status: OccurrenceStatus | None = Field(None, description="Status da ocorrência")
    occurred_at: datetime | None = Field(None, description="Data/hora da ocorrência")
    employee_id: str | None = Field(None, description="ID do funcionário")
    post_id: str | None = Field(None, description="ID do posto")
    patrol_round_id: str | None = Field(None, description="ID da ronda")
    witnesses: str | None = Field(None, description="Testemunhas")
    corrective_action: str | None = Field(None, description="Ação corretiva aplicada")
    is_active: bool | None = Field(None, description="Ativo/Inativo")


class OccurrenceResolve(BaseModel):
    """Schema para resolver uma ocorrência disciplinar."""

    corrective_action: str = Field(
        ..., min_length=10, description="Ação corretiva aplicada (advertência, suspensão, etc)"
    )
    resolution_notes: str | None = Field(None, description="Notas adicionais sobre a resolução")


class OccurrenceResponse(BaseModel):
    """Schema de resposta para Occurrence."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    title: str
    description: str
    occurrence_type: str
    severity: str
    category: str
    status: str

    # Envolvidos
    employee_id: str | None  # Funcionário envolvido (employees.id) — opcional
    inspector_id: str  # Gestor fiscalizador
    post_id: str  # Posto
    patrol_round_id: str | None  # Ronda relacionada
    witnesses: str | None  # Testemunhas

    # Datas
    occurred_at: datetime
    reported_at: datetime
    resolved_at: datetime | None

    # Resolução
    corrective_action: str | None  # Ação corretiva aplicada
    resolution_notes: str | None
    resolved_by_id: str | None

    # Evidências
    attachments: dict[str, Any] | None  # JSONB do banco

    # Controle
    is_active: bool
    created_at: datetime
    updated_at: datetime

    # Propriedades computadas
    is_resolved: bool
    is_severe: bool  # Se é grave/gravíssima
    resolution_time_hours: float | None


class OccurrenceListResponse(BaseModel):
    """Schema de resposta para listagem de Occurrences."""

    items: list[OccurrenceResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class OccurrenceFilter(BaseModel):
    """Schema para filtros de busca de Occurrences."""

    occurrence_type: OccurrenceType | None = None
    severity: OccurrenceSeverity | None = None
    category: OccurrenceCategory | None = None
    status: OccurrenceStatus | None = None
    employee_id: str | None = None  # Filtrar por funcionário
    inspector_id: str | None = None  # Filtrar por fiscalizador
    post_id: str | None = None
    patrol_round_id: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    search: str | None = None


class OccurrenceCommentCreate(BaseModel):
    """Schema para criação de comentário em uma ocorrência."""

    content: str = Field(..., min_length=2, description="Conteúdo do comentário")


class OccurrenceCommentResponse(BaseModel):
    """Schema de resposta para comentário de ocorrência."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    occurrence_id: str
    author_id: str
    author_name: str | None
    content: str
    is_internal: bool
    created_at: datetime


class OccurrenceStats(BaseModel):
    """Schema para estatísticas de Occurrences."""

    total: int = 0
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    by_category: dict[str, int] = {}
    open: int = 0
    in_analysis: int = 0
    resolved: int = 0
    severe: int = 0  # Graves + gravíssimas
    by_employee: dict[str, int] = {}  # Top funcionários com mais infrações
    avg_resolution_time_hours: float | None = None
