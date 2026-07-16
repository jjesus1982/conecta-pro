"""Schemas Pydantic para Férias e Afastamentos."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, model_validator


class VacationRequestCreate(BaseModel):
    """Schema para criar solicitação."""

    employee_id: str
    employee_name: str | None = None
    type: str = "ferias"
    start_date: date
    end_date: date
    reason: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _validar_periodo(self) -> "VacationRequestCreate":
        # término nunca antes do início (qualquer tipo)
        if self.end_date < self.start_date:
            raise ValueError("A data de término não pode ser anterior à data de início.")
        # FÉRIAS têm teto legal de 30 dias corridos (CLT art. 130). Afastamentos/licenças
        # (médica, maternidade, etc.) podem ultrapassar 30 dias, então só validamos férias.
        _t = (self.type or "").strip().lower()
        if _t in ("ferias", "férias", "vacation"):
            dias_corridos = (self.end_date - self.start_date).days + 1
            if dias_corridos > 30:
                raise ValueError(
                    f"Férias não podem exceder 30 dias corridos (CLT art. 130); "
                    f"o período informado tem {dias_corridos} dias."
                )
        return self


class VacationRequestUpdate(BaseModel):
    """Schema para atualizar solicitação."""

    type: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    reason: str | None = None
    notes: str | None = None
    status: str | None = None


class VacationRequestResponse(BaseModel):
    """Schema de resposta."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    employee_id: str
    employee_name: str | None = None
    type: str
    status: str
    start_date: date
    end_date: date
    days: str | None = None
    reason: str | None = None
    notes: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    rejected_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class VacationRequestListResponse(BaseModel):
    """Schema de resposta lista."""

    items: list[VacationRequestResponse]
    total: int
    pendente: int
    aprovado: int
    rejeitado: int
