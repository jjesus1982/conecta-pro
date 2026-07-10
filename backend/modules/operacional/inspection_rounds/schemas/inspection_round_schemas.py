"""
Schemas Pydantic para Rondas de Inspecao.

Author: Conecta PRO Team
Date: 2026-01-23
"""

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator

_TZ_MANAUS = ZoneInfo("America/Manaus")


def _naive_manaus(v: datetime | None) -> datetime | None:
    """Navegador manda ISO com 'Z' (aware); colunas são TIMESTAMP naive em hora de
    Manaus (doutrina do módulo). Sem isso o asyncpg estoura DataError → 500."""
    if isinstance(v, datetime) and v.tzinfo is not None:
        return v.astimezone(_TZ_MANAUS).replace(tzinfo=None)
    return v

# =============================================================================
# ENUMS PARA SCHEMAS
# =============================================================================


class InspectionRoundStatusEnum(str):
    AGENDADA = "agendada"
    EM_ANDAMENTO = "em_andamento"
    PAUSADA = "pausada"
    CONCLUIDA = "concluida"
    CANCELADA = "cancelada"


class InspectorRoleEnum(str):
    GERENTE_OPERACIONAL = "gerente_operacional"
    SUPERVISOR_OPERACIONAL = "supervisor_operacional"
    INSPETOR_OPERACIONAL = "inspetor_operacional"
    LIDER_SERVICO = "lider_servico"


class CheckpointTypeEnum(str):
    VERIFICACAO_POSTO = "verificacao_posto"
    VERIFICACAO_FUNCIONARIO = "verificacao_funcionario"
    REGISTRO_OCORRENCIA = "registro_ocorrencia"
    MEDIDA_DISCIPLINAR = "medida_disciplinar"
    OBSERVACAO_GERAL = "observacao_geral"
    FOTO_EVIDENCIA = "foto_evidencia"


class CheckpointStatusEnum(str):
    CONFORME = "conforme"
    NAO_CONFORME = "nao_conforme"
    PENDENTE = "pendente"
    COM_OCORRENCIA = "com_ocorrencia"


# =============================================================================
# CHECKPOINT SCHEMAS
# =============================================================================


class CheckpointCreate(BaseModel):
    """Schema para criacao de checkpoint."""

    post_id: UUID | None = None
    post_name: str | None = None
    client_id: UUID | None = None
    client_name: str | None = None
    checkpoint_type: str = Field(default="verificacao_posto")
    status: str = Field(default="pendente")
    employee_id: UUID | None = None
    employee_name: str | None = None
    employee_cpf: str | None = None
    employee_position: str | None = None
    title: str | None = None
    description: str | None = None
    observations: str | None = None
    infraction_category: str | None = None
    infraction_severity: str | None = None
    photos: list[dict] | None = None
    latitude: float | None = None
    longitude: float | None = None


class CheckpointUpdate(BaseModel):
    """Schema para atualizacao de checkpoint."""

    status: str | None = None
    description: str | None = None
    observations: str | None = None
    infraction_category: str | None = None
    infraction_severity: str | None = None
    photos: list[dict] | None = None


class CheckpointResponse(BaseModel):
    """Schema de resposta de checkpoint."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    inspection_round_id: UUID
    post_id: UUID | None = None
    post_name: str | None = None
    client_id: UUID | None = None
    client_name: str | None = None
    checkpoint_type: str
    status: str
    employee_id: UUID | None = None
    employee_name: str | None = None
    employee_cpf: str | None = None
    employee_position: str | None = None
    occurrence_id: UUID | None = None
    occurrence_code: str | None = None
    disciplinary_action_id: UUID | None = None
    disciplinary_action_code: str | None = None
    disciplinary_action_type: str | None = None
    title: str | None = None
    description: str | None = None
    observations: str | None = None
    infraction_category: str | None = None
    infraction_severity: str | None = None
    photos: list[dict] | None = None
    latitude: float | None = None
    longitude: float | None = None
    sequence: int
    created_at: datetime


class CheckpointWithOccurrence(CheckpointResponse):
    """Checkpoint com detalhes da ocorrencia."""

    occurrence_title: str | None = None
    occurrence_status: str | None = None
    disciplinary_action_status: str | None = None


# =============================================================================
# INSPECTION ROUND SCHEMAS
# =============================================================================


class InspectionRoundCreate(BaseModel):
    """Schema para criacao de ronda."""

    tenant_id: UUID
    inspector_id: UUID
    inspector_name: str = Field(..., min_length=2, max_length=255)
    inspector_role: str = Field(default="supervisor_operacional")
    scheduled_date: datetime | None = None
    posts_to_visit: list[UUID] | None = None
    observations: str | None = None

    _tz = field_validator("scheduled_date")(_naive_manaus)


class InspectionRoundUpdate(BaseModel):
    """Schema para atualizacao de ronda."""

    scheduled_date: datetime | None = None
    posts_to_visit: list[UUID] | None = None
    observations: str | None = None
    summary: str | None = None

    _tz = field_validator("scheduled_date")(_naive_manaus)


class InspectionRoundResponse(BaseModel):
    """Schema de resposta de ronda."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    tenant_id: UUID
    inspector_id: UUID
    inspector_name: str
    inspector_role: str
    status: str
    scheduled_date: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_minutes: int | None = None
    posts_to_visit: list[str] | None = None
    posts_visited: list[str] | None = None
    total_checkpoints: int
    total_occurrences: int
    total_disciplinary_actions: int
    total_employees_checked: int
    observations: str | None = None
    summary: str | None = None
    start_latitude: float | None = None
    start_longitude: float | None = None
    end_latitude: float | None = None
    end_longitude: float | None = None
    total_distance_km: float | None = None
    progress_percentage: float = 0.0
    is_active: bool
    created_at: datetime
    updated_at: datetime
    checkpoints: list[CheckpointResponse] | None = None


class InspectionRoundSummary(BaseModel):
    """Resumo de ronda para listagem."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    inspector_name: str
    inspector_role: str
    status: str
    scheduled_date: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    total_checkpoints: int
    total_occurrences: int
    total_disciplinary_actions: int
    progress_percentage: float = 0.0
    created_at: datetime


class InspectionRoundListResponse(BaseModel):
    """Resposta paginada de rondas."""

    items: list[InspectionRoundSummary]
    total: int
    page: int
    page_size: int
    pages: int


class InspectionRoundFilter(BaseModel):
    """Filtros para listagem de rondas."""

    inspector_id: UUID | None = None
    inspector_role: str | None = None
    status: str | None = None
    post_id: UUID | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    has_occurrences: bool | None = None
    has_disciplinary_actions: bool | None = None


# =============================================================================
# ACTION SCHEMAS
# =============================================================================


class StartRoundRequest(BaseModel):
    """Request para iniciar ronda."""

    latitude: float | None = None
    longitude: float | None = None


class CompleteRoundRequest(BaseModel):
    """Request para concluir ronda."""

    summary: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class RegisterOccurrenceRequest(BaseModel):
    """Request para registrar ocorrencia durante ronda."""

    post_id: UUID
    post_name: str
    employee_id: UUID | None = None
    employee_name: str | None = None
    employee_cpf: str | None = None
    employee_position: str | None = None

    # Dados da ocorrencia
    title: str = Field(..., min_length=5, max_length=200)
    description: str = Field(..., min_length=10)
    category: str = Field(default="comportamento")
    severity: str = Field(default="media")
    type: str = Field(default="incidente")
    priority: str = Field(default="normal")

    # Localizacao
    latitude: float | None = None
    longitude: float | None = None
    location_description: str | None = None

    # Fotos
    photos: list[dict] | None = None


class ApplyDisciplinaryRequest(BaseModel):
    """Request para aplicar medida disciplinar durante ronda."""

    # Checkpoint/Ocorrencia de origem
    checkpoint_id: UUID | None = None
    occurrence_id: UUID | None = None

    # Dados do funcionario
    employee_id: UUID
    employee_name: str
    employee_cpf: str
    employee_position: str | None = None
    employee_admission_date: datetime | None = None

    # Local
    post_id: UUID
    client_id: UUID | None = None

    # Tipo de medida
    action_type: str = Field(..., description="advertencia_verbal, advertencia_escrita, suspensao")

    # Motivo
    reason_category: str = Field(..., description="falta, atraso, insubordinacao, indisciplina, negligencia, etc")
    reason_description: str = Field(..., min_length=20)

    # Data do incidente
    incident_date: datetime

    # Suspensao (se aplicavel)
    suspension_days: int | None = Field(None, ge=1, le=30)
    suspension_start_date: datetime | None = None

    # Testemunhas
    witness_1_name: str | None = None
    witness_1_cpf: str | None = None
    witness_2_name: str | None = None
    witness_2_cpf: str | None = None


class RegisterOccurrenceResponse(BaseModel):
    """Response para registro de ocorrência durante ronda."""

    model_config = ConfigDict(from_attributes=True)

    success: bool = Field(..., description="Se o registro foi bem-sucedido")
    occurrence_id: UUID = Field(..., description="ID da ocorrência criada")
    checkpoint_id: UUID | None = Field(None, description="ID do checkpoint atualizado")
    message: str = Field(default="Ocorrência registrada com sucesso")

    # Dados da ocorrência criada
    occurrence_type: str | None = None
    severity: str | None = None
    status: str | None = None
    created_at: datetime | None = None


class ApplyDisciplinaryResponse(BaseModel):
    """Response para aplicação de medida disciplinar durante ronda."""

    model_config = ConfigDict(from_attributes=True)

    success: bool = Field(..., description="Se a aplicação foi bem-sucedida")
    disciplinary_action_id: UUID = Field(..., description="ID da medida disciplinar criada")
    occurrence_id: UUID | None = Field(None, description="ID da ocorrência vinculada")
    checkpoint_id: UUID | None = Field(None, description="ID do checkpoint vinculado")
    message: str = Field(default="Medida disciplinar aplicada com sucesso")

    # Dados da medida criada
    action_type: str | None = None
    status: str | None = None
    employee_name: str | None = None
    created_at: datetime | None = None


# =============================================================================
# DASHBOARD SCHEMAS
# =============================================================================


class InspectorStats(BaseModel):
    """Estatisticas por inspetor."""

    inspector_id: UUID
    inspector_name: str
    inspector_role: str
    total_rounds: int
    total_occurrences: int
    total_disciplinary_actions: int
    avg_duration_minutes: float
    last_round_date: datetime | None = None


class InspectionDashboardStats(BaseModel):
    """Estatisticas do dashboard de rondas."""

    # Resumo geral
    total_rounds: int
    rounds_in_progress: int
    rounds_completed: int
    rounds_scheduled: int

    # Ocorrencias
    total_occurrences: int
    occurrences_pending: int
    occurrences_resolved: int

    # Medidas disciplinares
    total_disciplinary_actions: int
    warnings_count: int
    suspensions_count: int

    # Por periodo
    rounds_today: int
    rounds_this_week: int
    rounds_this_month: int

    # Top inspetores
    top_inspectors: list[InspectorStats]

    # Postos mais visitados
    most_visited_posts: list[dict]

    # Categorias de infracoes mais comuns
    top_infraction_categories: list[dict]
