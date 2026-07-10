"""
Schemas Pydantic para Relatorios Operacionais.
"""

from datetime import date

from pydantic import BaseModel, Field


class CoverageReportItem(BaseModel):
    """Item de cobertura por posto."""

    post_id: str
    post_name: str
    required_headcount: int = Field(0, description="Quadro requerido do posto (0 = sem quadro presencial)")
    total_allocations: int
    active_allocations: int
    coverage_rate: float = Field(..., description="Percentual de cobertura (alocacoes ativas / quadro requerido)")


class CoverageReportResponse(BaseModel):
    """Resposta do relatorio de cobertura."""

    start_date: date
    end_date: date
    total_posts: int = Field(..., description="Postos ativos (status='active')")
    covered_posts: int = Field(0, description="Postos ativos com quadro preenchido")
    total_allocations: int
    active_allocations: int
    coverage_rate: float = Field(..., description="Postos ativos cobertos / postos ativos x 100")
    items: list[CoverageReportItem]


class HoursReportItem(BaseModel):
    """Item de horas por funcionario."""

    employee_id: str
    employee_name: str = Field("—", description="Nome do funcionario (nunca e-mail/UUID)")
    total_shifts: int
    total_hours: float
    overtime_hours: float


class HoursReportResponse(BaseModel):
    """Resposta do relatorio de horas trabalhadas."""

    start_date: date
    end_date: date
    total_employees: int
    total_hours: float
    total_overtime: float
    items: list[HoursReportItem]


class CostsReportItem(BaseModel):
    """Item de custos por posto."""

    post_id: str
    post_name: str
    total_shifts: int
    total_cost: float
    total_hours_ponto: float | None = None
    fonte_custo: str | None = None


class CostsReportResponse(BaseModel):
    """Resposta do relatorio de custos estimados."""

    start_date: date
    end_date: date
    total_posts: int
    total_cost: float
    items: list[CostsReportItem]
