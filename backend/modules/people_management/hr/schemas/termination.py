"""
Schemas Pydantic para TerminationProcess (Processo de Rescisão).
"""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from modules.people_management.hr.models.termination import (
    TerminationStatus,
    TerminationType,
)


class TerminationCreate(BaseModel):
    """Schema para criação de processo de rescisão."""

    employee_id: str
    type: TerminationType
    reason: str | None = None
    notice_period_days: int | None = Field(None, ge=0, le=90)
    notice_start_date: date | None = None
    last_working_day: date | None = None
    notes: str | None = None
    # Tipo de aviso prévio: "trabalhado" (funcionário cumpre) ou "indenizado" (empresa paga)
    # Armazenado no campo reason como "notice_type:<valor>" quando reason não é fornecido
    notice_type: str | None = None
    status: TerminationStatus | None = None


class TerminationUpdate(BaseModel):
    """Schema para atualização de processo de rescisão."""

    status: TerminationStatus | None = None
    reason: str | None = None
    notice_period_days: int | None = Field(None, ge=0, le=90)
    notice_start_date: date | None = None
    last_working_day: date | None = None
    exit_interview_done: bool | None = None
    exit_interview_notes: str | None = None
    esocial_event_sent: bool | None = None
    # Aceita tanto lista de nomes de documentos (["TRCT", ...]) quanto
    # dicionário (compatibilidade com registros antigos que gravaram {}).
    documents_generated: list | dict | None = None
    notes: str | None = None


class TerminationCalculation(BaseModel):
    """Schema para detalhamento dos cálculos rescisórios."""

    model_config = ConfigDict(from_attributes=True)

    employee_id: str
    employee_name: str
    termination_type: str
    last_working_day: date | None = None
    months_worked: int = 0

    # Verbas rescisórias
    saldo_salario: float = 0.0
    aviso_previo_indenizado: float = 0.0
    ferias_vencidas: float = 0.0
    ferias_proporcionais: float = 0.0
    terco_constitucional: float = 0.0
    decimo_terceiro_proporcional: float = 0.0
    fgts_mes_rescisao: float = 0.0
    multa_fgts_40: float = 0.0

    # Totais
    total_proventos: float = 0.0
    total_descontos: float = 0.0
    total_liquido: float = 0.0


class TerminationResponse(BaseModel):
    """Schema de resposta para processo de rescisão."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    employee_id: UUID
    type: str
    reason: str | None = None
    notice_period_days: int | None = None
    notice_start_date: date | None = None
    last_working_day: date | None = None
    status: str
    severance_amount: float | None = None
    vacation_balance_amount: float | None = None
    thirteenth_salary_amount: float | None = None
    fgts_amount: float | None = None
    total_amount: float | None = None
    exit_interview_done: bool = False
    exit_interview_notes: str | None = None
    esocial_event_sent: bool = False
    # Banco guarda lista (["TRCT", "eSocial S-2299"]) para rescisões concluídas
    # e {} para as iniciadas — aceitar ambos evita ResponseValidationError.
    documents_generated: list | dict | None = None
    created_by_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
