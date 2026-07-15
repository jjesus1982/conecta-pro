"""
Schemas Pydantic para EmploymentContract (Contrato de Trabalho).
"""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from modules.people_management.hr.models.contract import ContractType


class ContractCreate(BaseModel):
    """Schema para criação de contrato de trabalho."""

    employee_id: str | UUID
    type: ContractType
    start_date: date
    end_date: date | None = None
    work_schedule: str | None = Field(None, max_length=30)
    weekly_hours: float | None = Field(None, ge=0, le=44)
    base_salary: float = Field(..., ge=0)
    hazard_pay_percent: float | None = Field(None, ge=0, le=100)
    unhealthy_pay_percent: float | None = Field(None, ge=0, le=100)
    night_shift_percent: float | None = Field(None, ge=0, le=100)
    job_title: str | None = None
    department: str | None = None
    cost_center: str | None = None
    workplace_id: str | None = None
    union_name: str | None = None
    union_code: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _validar_datas_e_prazo(self) -> "ContractCreate":
        # data invertida
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("Data de término (end_date) não pode ser anterior à admissão (start_date).")
        # contrato por prazo DETERMINADO/TEMPORÁRIO exige término (senão vira 'determinado eterno')
        if self.type in (ContractType.CLT_DETERMINATE, ContractType.TEMPORARY) and self.end_date is None:
            raise ValueError(
                f"Contrato do tipo '{self.type.value}' (prazo determinado) exige data de término (end_date)."
            )
        return self


class ContractUpdate(BaseModel):
    """Schema para atualização de contrato de trabalho."""

    end_date: date | None = None
    work_schedule: str | None = Field(None, max_length=30)
    weekly_hours: float | None = Field(None, ge=0, le=44)
    base_salary: float | None = Field(None, ge=0)
    hazard_pay_percent: float | None = Field(None, ge=0, le=100)
    unhealthy_pay_percent: float | None = Field(None, ge=0, le=100)
    night_shift_percent: float | None = Field(None, ge=0, le=100)
    job_title: str | None = None
    department: str | None = None
    cost_center: str | None = None
    workplace_id: str | None = None
    union_name: str | None = None
    union_code: str | None = None
    is_current: bool | None = None
    notes: str | None = None
    document_path: str | None = None
    signed_at: datetime | None = None


class ContractResponse(BaseModel):
    """Schema de resposta para contrato de trabalho."""

    model_config = ConfigDict(from_attributes=True)

    id: str | UUID
    employee_id: str | UUID
    type: str
    start_date: date
    end_date: date | None = None
    work_schedule: str | None = None
    weekly_hours: float | None = None
    base_salary: float
    hazard_pay_percent: float | None = None
    unhealthy_pay_percent: float | None = None
    night_shift_percent: float | None = None
    job_title: str | None = None
    department: str | None = None
    cost_center: str | None = None
    workplace_id: str | None = None
    union_name: str | None = None
    union_code: str | None = None
    is_current: bool = True
    # ORM devolve UUID; aceitar str | UUID evita ResponseValidationError que
    # quebrava a lista inteira quando algum contrato tinha previous_contract_id.
    previous_contract_id: str | UUID | None = None
    notes: str | None = None
    document_path: str | None = None
    signed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
