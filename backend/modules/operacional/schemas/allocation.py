"""
Schemas Pydantic para Allocation (Alocação Funcionário-Posto).
"""

from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from modules.operacional.models.allocation import AllocationStatus


class AllocationBase(BaseModel):
    """Schema base para Allocation."""

    post_id: str = Field(..., description="ID do posto")
    employee_id: str = Field(..., description="ID do funcionário")
    start_date: date = Field(..., description="Data de início")
    end_date: date | None = Field(None, description="Data de fim (null = indeterminado)")
    is_primary: bool = Field(default=True, description="É alocação principal")
    is_temporary: bool = Field(default=False, description="É temporária")
    setor: str | None = Field(None, max_length=30, description="Setor (PORTARIA/RONDISTA/SERVICOS GERAIS/INSALUBRIDADE)")
    role: str | None = Field(None, max_length=100, description="Função")
    notes: str | None = Field(None, description="Observações")

    @field_validator("post_id", "employee_id")
    @classmethod
    def validate_uuid(cls, v: str) -> str:
        """Valida se ID é um UUID válido."""
        try:
            UUID(v)
            return v
        except (ValueError, AttributeError):
            raise ValueError(f"ID inválido: {v}. Deve ser um UUID válido.")

    @field_validator("start_date")
    @classmethod
    def validate_start_date(cls, v: date) -> date:
        """Valida data de início."""
        today = date.today()
        max_past = today - timedelta(days=730)  # Máximo 2 anos no passado
        max_future = today + timedelta(days=365)  # Máximo 1 ano no futuro

        if v < max_past:
            raise ValueError(
                f"Data de início muito antiga. Máximo permitido: {max_past.isoformat()}. "
                "Para alocações históricas, contate o administrador."
            )
        if v > max_future:
            raise ValueError(f"Data de início muito futura. Máximo permitido: {max_future.isoformat()}")

        return v

    @model_validator(mode="after")
    def validate_dates(self) -> "AllocationBase":
        """Valida range de datas."""
        if self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date deve ser anterior a end_date")

        # Validar duração máxima
        if self.end_date:
            duration = self.end_date - self.start_date
            if duration > timedelta(days=1825):  # 5 anos
                raise ValueError("Duração da alocação não pode exceder 5 anos")

        return self


class AllocationCreate(AllocationBase):
    """Schema para criação de Allocation."""

    hourly_rate: float = Field(default=0.0, ge=0, le=500, description="Valor hora (máx R$ 500)")
    monthly_salary: float = Field(default=0.0, ge=0, le=50000, description="Salário mensal (máx R$ 50k)")
    additional_benefits: float = Field(default=0.0, ge=0, le=20000, description="Benefícios (máx R$ 20k)")
    qualifications: dict[str, Any] | list | None = Field(None, description="Qualificações")

    @model_validator(mode="after")
    def validate_compensation(self) -> "AllocationCreate":
        """Valida valores de compensação."""
        # Se informar hourly_rate e monthly_salary, deve ser consistente
        if self.hourly_rate > 0 and self.monthly_salary > 0:
            # 220 horas/mês é padrão
            expected_monthly = self.hourly_rate * 220
            tolerance = expected_monthly * 0.2  # 20% tolerância
            if abs(self.monthly_salary - expected_monthly) > tolerance:
                raise ValueError(
                    f"Valores inconsistentes: hourly_rate (R$ {self.hourly_rate:.2f}) e "
                    f"monthly_salary (R$ {self.monthly_salary:.2f}) não batem. "
                    f"Esperado aproximadamente R$ {expected_monthly:.2f} mensal."
                )
        return self


class AllocationUpdate(BaseModel):
    """Schema para atualização parcial de Allocation."""

    status: AllocationStatus | None = None
    end_date: date | None = None
    is_primary: bool | None = None
    is_temporary: bool | None = None
    setor: str | None = None
    hourly_rate: float | None = Field(None, ge=0)
    monthly_salary: float | None = Field(None, ge=0)
    additional_benefits: float | None = Field(None, ge=0)
    role: str | None = Field(None, max_length=100)
    qualifications: dict[str, Any] | list | None = None
    notes: str | None = None
    termination_reason: str | None = Field(None, max_length=255)
    is_active: bool | None = None


class AllocationResponse(BaseModel):
    """Schema de resposta para Allocation."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    post_id: str
    employee_id: str
    status: str
    start_date: date
    end_date: date | None
    is_primary: bool
    is_temporary: bool
    setor: str | None = None
    hourly_rate: float
    monthly_salary: float
    additional_benefits: float
    role: str | None
    qualifications: dict[str, Any] | list | None
    notes: str | None
    termination_reason: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    # Propriedades calculadas
    is_current: bool
    days_allocated: int
    total_monthly_cost: float

    # Dados denormalizados do funcionário
    employee_name: str | None = None
    employee_matricula: str | None = None
    employee_cargo: str | None = None

    # Dados denormalizados do posto
    post_name: str | None = None
    post_code: str | None = None


class AllocationListResponse(BaseModel):
    """Schema para listagem paginada de Allocations."""

    items: list[AllocationResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class AllocationFilter(BaseModel):
    """Schema para filtros de busca de Allocations."""

    post_id: str | None = None
    employee_id: str | None = None
    status: AllocationStatus | None = None
    is_primary: bool | None = None
    is_temporary: bool | None = None
    setor: str | None = None
    is_current: bool | None = None
    start_date_from: date | None = None
    start_date_to: date | None = None


class AllocationTerminate(BaseModel):
    """Schema para encerramento de alocação."""

    end_date: date = Field(..., description="Data de encerramento")
    termination_reason: str = Field(..., max_length=255, description="Motivo")
    notes: str | None = Field(None, description="Observações")


class AllocationBulkDelete(BaseModel):
    """Schema para deleção em lote de alocações."""

    allocation_ids: list[str] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Lista de IDs para deletar (máximo 100)",
    )


class AllocationBulkUpdateItem(BaseModel):
    """Item individual para atualização em lote."""

    allocation_id: str = Field(..., description="ID da alocação")
    data: AllocationUpdate = Field(..., description="Dados para atualização")


class AllocationBulkUpdate(BaseModel):
    """Schema para atualização em lote de alocações."""

    items: list[AllocationBulkUpdateItem] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Lista de alocações para atualizar (máximo 100)",
    )


class AllocationBulkOperationResult(BaseModel):
    """Resultado de operação em lote."""

    success_count: int = Field(..., description="Quantidade de sucessos")
    error_count: int = Field(..., description="Quantidade de erros")
    errors: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Lista de erros (ID + mensagem)",
    )
