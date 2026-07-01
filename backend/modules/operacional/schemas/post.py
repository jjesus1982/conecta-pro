"""
Schemas Pydantic para Post (Posto de Trabalho).
"""

from datetime import datetime, time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from modules.operacional.models.post import PostStatus, PostType, ShiftType


class PostBase(BaseModel):
    """Schema base para Post."""

    name: str = Field(..., min_length=2, max_length=255, description="Nome do posto")
    description: str | None = Field(None, description="Descrição")
    post_type: PostType = Field(default=PostType.PORTEIRO, description="Tipo de posto")
    shift_type: ShiftType = Field(default=ShiftType.DIURNO, description="Tipo de turno")

    # Localização
    address: str | None = Field(None, max_length=500, description="Endereço")
    city: str | None = Field(None, max_length=100, description="Cidade")
    state: str | None = Field(None, max_length=2, description="UF")
    zip_code: str | None = Field(None, max_length=10, description="CEP")
    latitude: float | None = Field(None, ge=-90, le=90, description="Latitude")
    longitude: float | None = Field(None, ge=-180, le=180, description="Longitude")

    # Horários (nomes conforme schema do banco)
    shift_start_time: time | None = Field(None, description="Hora início do turno")
    shift_end_time: time | None = Field(None, description="Hora fim do turno")
    break_duration_minutes: int = Field(default=60, ge=0, description="Intervalo em minutos")
    night_shift_bonus_percent: float = Field(default=20.0, ge=0, description="Adicional noturno %")
    hazard_pay_percent: float = Field(default=0.0, ge=0, description="Periculosidade %")

    # Capacidade e Custos
    required_headcount: int = Field(default=1, ge=1, description="Quantidade necessária de funcionários")
    requires_experience_months: int = Field(default=0, ge=0, description="Experiência mínima em meses")
    hourly_rate: float = Field(default=0.0, ge=0, description="Valor hora")
    monthly_cost: float = Field(default=0.0, ge=0, description="Custo mensal")

    # Configurações
    requires_armed: bool = Field(default=False, description="Requer armamento")
    requires_vehicle: bool = Field(default=False, description="Requer veículo")

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: str | None) -> str | None:
        """Valida UF."""
        if v is not None:
            return v.upper()
        return v

    @field_validator("zip_code")
    @classmethod
    def validate_zip_code(cls, v: str | None) -> str | None:
        """Valida CEP."""
        if v is not None:
            digits = "".join(c for c in v if c.isdigit())
            if len(digits) != 8:
                raise ValueError("CEP deve ter 8 dígitos")
        return v

    @field_validator("night_shift_bonus_percent", "hazard_pay_percent")
    @classmethod
    def validate_percent(cls, v: float) -> float:
        """Valida percentuais."""
        if v < 0:
            raise ValueError("Percentual não pode ser negativo")
        if v > 100:
            raise ValueError("Percentual não pode ser maior que 100%")
        return v

    @field_validator("hourly_rate")
    @classmethod
    def validate_hourly_rate(cls, v: float) -> float:
        """Valida valor hora."""
        if v < 0:
            raise ValueError("Valor hora não pode ser negativo")
        if v > 1000:  # R$ 1000/hora é um limite razoável
            raise ValueError("Valor hora muito alto. Máximo permitido: R$ 1000/hora")
        return v

    @field_validator("monthly_cost")
    @classmethod
    def validate_monthly_cost(cls, v: float) -> float:
        """Valida custo mensal."""
        if v < 0:
            raise ValueError("Custo mensal não pode ser negativo")
        if v > 100000:  # R$ 100k/mês é um limite razoável para um posto
            raise ValueError("Custo mensal muito alto. Máximo permitido: R$ 100.000/mês")
        return v

    @field_validator("required_headcount")
    @classmethod
    def validate_headcount(cls, v: int) -> int:
        """Valida quantidade necessária."""
        if v < 1:
            raise ValueError("Quantidade necessária deve ser no mínimo 1")
        if v > 50:  # 50 pessoas é um limite razoável para um posto
            raise ValueError("Quantidade muito alta. Máximo permitido: 50 funcionários por posto")
        return v


class PostCreate(PostBase):
    """
    Schema para criação de Post.

    Um posto de trabalho representa uma posição operacional onde funcionários
    são alocados para realizar atividades de portaria, controle de acesso ou serviços.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Portaria Principal Shopping Center",
                "description": "Controle de acesso principal do shopping",
                "post_type": "PORTEIRO",
                "shift_type": "DIURNO",
                "address": "Av. Paulista, 1000",
                "city": "São Paulo",
                "state": "SP",
                "zip_code": "01310-100",
                "shift_start_time": "08:00:00",
                "shift_end_time": "17:00:00",
                "break_duration_minutes": 60,
                "required_headcount": 2,
                "requires_armed": False,
                "requires_vehicle": False,
                "hourly_rate": 25.50,
                "monthly_cost": 8000.00,
            }
        }
    )

    contract_id: str | None = Field(None, description="ID do contrato")
    client_id: str | None = Field(None, description="ID do cliente")
    required_certifications: dict[str, Any] | None = Field(None, description="Certificações necessárias")
    supervisor_name: str | None = Field(None, max_length=200, description="Nome do supervisor")
    supervisor_phone: str | None = Field(None, max_length=20, description="Telefone do supervisor")
    emergency_contact: str | None = Field(None, max_length=200, description="Contato de emergência")
    emergency_phone: str | None = Field(None, max_length=20, description="Telefone de emergência")
    notes: str | None = Field(None, description="Observações")


class PostUpdate(BaseModel):
    """
    Schema para atualização parcial de Post.

    Todos os campos são opcionais. Apenas os campos fornecidos serão atualizados.
    """

    name: str | None = Field(None, min_length=2, max_length=255, description="Nome do posto")
    description: str | None = Field(None, description="Descrição")
    post_type: PostType | None = Field(None, description="Tipo de posto")
    status: PostStatus | None = Field(None, description="Status do posto")
    shift_type: ShiftType | None = Field(None, description="Tipo de turno")
    contract_id: str | None = Field(None, description="ID do contrato")
    client_id: str | None = Field(None, description="ID do cliente")
    address: str | None = Field(None, max_length=500, description="Endereço")
    city: str | None = Field(None, max_length=100, description="Cidade")
    state: str | None = Field(None, max_length=2, description="UF")
    zip_code: str | None = Field(None, max_length=10, description="CEP")
    latitude: float | None = Field(None, ge=-90, le=90, description="Latitude")
    longitude: float | None = Field(None, ge=-180, le=180, description="Longitude")
    shift_start_time: time | None = Field(None, description="Hora início do turno")
    shift_end_time: time | None = Field(None, description="Hora fim do turno")
    break_duration_minutes: int | None = Field(None, ge=0, description="Intervalo em minutos")
    night_shift_bonus_percent: float | None = Field(None, ge=0, description="Adicional noturno %")
    hazard_pay_percent: float | None = Field(None, ge=0, description="Periculosidade %")
    required_headcount: int | None = Field(None, ge=1, description="Quantidade necessária")
    requires_experience_months: int | None = Field(None, ge=0, description="Experiência mínima em meses")
    hourly_rate: float | None = Field(None, ge=0, description="Valor hora")
    monthly_cost: float | None = Field(None, ge=0, description="Custo mensal")
    requires_armed: bool | None = Field(None, description="Requer armamento")
    requires_vehicle: bool | None = Field(None, description="Requer veículo")
    required_certifications: dict[str, Any] | None = Field(None, description="Certificações necessárias")
    supervisor_name: str | None = Field(None, max_length=200, description="Nome do supervisor")
    supervisor_phone: str | None = Field(None, max_length=20, description="Telefone do supervisor")
    emergency_contact: str | None = Field(None, max_length=200, description="Contato de emergência")
    emergency_phone: str | None = Field(None, max_length=20, description="Telefone de emergência")
    notes: str | None = Field(None, description="Observações")
    is_active: bool | None = Field(None, description="Ativo/Inativo")


class PostResponse(BaseModel):
    """Schema de resposta para Post."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    name: str
    description: str | None
    post_type: str
    status: str
    shift_type: str
    contract_id: str | None
    client_id: str | None
    address: str | None
    city: str | None
    state: str | None
    zip_code: str | None
    latitude: float | None
    longitude: float | None
    shift_start_time: time | None
    shift_end_time: time | None
    break_duration_minutes: int
    night_shift_bonus_percent: float
    hazard_pay_percent: float
    required_certifications: dict[str, Any] | None
    required_headcount: int
    current_headcount: int
    requires_experience_months: int
    hourly_rate: float
    monthly_cost: float
    requires_armed: bool
    requires_vehicle: bool
    supervisor_name: str | None
    supervisor_phone: str | None
    emergency_contact: str | None
    emergency_phone: str | None
    notes: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    # Propriedades calculadas
    is_filled: bool
    vacancy_count: int
    daily_hours: float


class PostListResponse(BaseModel):
    """Schema para listagem paginada de Posts."""

    items: list[PostResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class PostFilter(BaseModel):
    """Schema para filtros de busca de Posts."""

    post_type: PostType | None = None
    status: PostStatus | None = None
    shift_type: ShiftType | None = None
    contract_id: str | None = None
    client_id: str | None = None
    city: str | None = None
    state: str | None = None
    requires_armed: bool | None = None
    requires_vehicle: bool | None = None
    has_vacancy: bool | None = None
    search: str | None = Field(None, description="Busca por nome ou código")


class PostStats(BaseModel):
    """Estatísticas de postos."""

    total: int
    by_status: dict[str, int]
    by_type: dict[str, int]
    by_shift: dict[str, int]
    filled: int
    with_vacancy: int
    total_headcount: int
    total_allocated: int
    total_monthly_cost: float
