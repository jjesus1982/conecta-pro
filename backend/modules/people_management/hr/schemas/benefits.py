from uuid import UUID

"""
Schemas Pydantic para EmployeeBenefit (Benefícios).
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from modules.people_management.hr.models.benefits import BenefitStatus, BenefitType


class BenefitCreate(BaseModel):
    """Schema para criação de benefício."""

    employee_id: UUID
    type: BenefitType
    provider: str | None = None
    plan_name: str | None = None
    employee_contribution: float | None = Field(None, ge=0)
    company_contribution: float | None = Field(None, ge=0)
    start_date: date | None = None
    end_date: date | None = None
    card_number: str | None = None
    notes: str | None = None


class BenefitUpdate(BaseModel):
    """Schema para atualização de benefício."""

    provider: str | None = None
    plan_name: str | None = None
    employee_contribution: float | None = Field(None, ge=0)
    company_contribution: float | None = Field(None, ge=0)
    start_date: date | None = None
    end_date: date | None = None
    status: BenefitStatus | None = None
    card_number: str | None = None
    notes: str | None = None


class BenefitResponse(BaseModel):
    """Schema de resposta para benefício."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    employee_id: UUID
    employee_name: str | None = None
    type: str
    provider: str | None = None
    plan_name: str | None = None
    employee_contribution: float | None = None
    company_contribution: float | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: str
    card_number: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
