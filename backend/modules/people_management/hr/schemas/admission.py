"""
Schemas Pydantic para AdmissionProcess (Processo de Admissao).
"""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from modules.people_management.hr.models.admission import AdmissionStatus


class AdmissionProcessCreate(BaseModel):
    """Schema para criacao de processo de admissao."""

    candidate_name: str = Field(..., min_length=2, max_length=200)
    cpf: str = Field(..., min_length=11, max_length=20)
    position: str = Field(..., min_length=2, max_length=100)
    department: str | None = Field(None, max_length=100)
    salary_proposed: float | None = Field(None, ge=0)
    expected_start_date: date | None = None
    contract_type: str | None = Field("CLT", max_length=20)
    candidate_id: str | None = None
    job_position_id: str | None = None
    cct_cargo_id: str | None = Field(None, description="UUID do cargo na CCT (fonte única do piso)")
    workplace_id: str | None = None
    checklist: dict | None = None
    notes: str | None = None
    # Dados do candidato coletados no form. admission_processes NÃO tem colunas
    # próprias p/ estes campos, então são persistidos em documents_received._dados_candidato
    # (JSONB) — não são descartados. Migram p/ o Employee (pis, data_nascimento) na conclusão.
    pis_pasep: str | None = Field(None, max_length=20, description="PIS/PASEP/NIS do candidato")
    birth_date: date | None = Field(None, description="Data de nascimento do candidato")


class AdmissionProcessUpdate(BaseModel):
    """Schema para atualizacao de processo de admissao."""

    candidate_name: str | None = None
    cpf: str | None = None
    position: str | None = None
    department: str | None = None
    status: AdmissionStatus | None = None
    expected_start_date: date | None = None
    actual_start_date: date | None = None
    salary_proposed: float | None = Field(None, ge=0)
    contract_type: str | None = None
    workplace_id: str | None = None
    cct_cargo_id: str | None = Field(None, description="UUID do cargo na CCT")
    checklist: dict | None = None
    documents_received: dict | None = None
    medical_exam_date: date | None = None
    medical_exam_result: str | None = None
    contract_signed_at: datetime | None = None
    employee_id: str | None = None
    notes: str | None = None


class AdmissionProcessResponse(BaseModel):
    """Schema de resposta para processo de admissao."""

    model_config = ConfigDict(from_attributes=True)

    id: str | UUID
    candidate_name: str | None = None
    cpf: str | None = None
    position: str | None = None
    department: str | None = None
    candidate_id: str | UUID | None = None
    employee_id: str | UUID | None = None
    job_position_id: str | UUID | None = None
    status: str
    expected_start_date: date | None = None
    actual_start_date: date | None = None
    salary_proposed: float | None = None
    contract_type: str | None = None
    workplace_id: str | UUID | None = None
    checklist: dict | None = None
    documents_received: dict | None = None
    medical_exam_date: date | None = None
    medical_exam_result: str | None = None
    contract_signed_at: datetime | None = None
    notes: str | None = None
    created_by_id: str | UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
