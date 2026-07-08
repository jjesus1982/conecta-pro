"""Pydantic schemas para SST."""

from pydantic import BaseModel, Field


class ASOCreate(BaseModel):
    employee_id: str
    tipo: str = Field(..., description="admissional|periodico|demissional|retorno_trabalho|mudanca_funcao")
    data_agendamento: str
    clinica: str | None = None


class ASOResultUpdate(BaseModel):
    apto: bool
    restricoes: list[str] = []
    medico: str | None = None
    crm: str | None = None
    observacoes: str | None = None


class ASOResponse(BaseModel):
    aso_id: str
    employee_id: str
    tipo: str
    status: str
    data_agendamento: str | None = None
    apto: bool | None = None
    restricoes: list[str] = []
    model_config = {"from_attributes": True}


class EPIDeliveryCreate(BaseModel):
    employee_id: str
    epi_nome: str
    quantidade: int = 1
    epi_ca: str | None = None


class EPIDeliveryResponse(BaseModel):
    delivery_id: str
    employee_id: str
    epi: str
    quantidade: int
    data_entrega: str
    data_validade: str | None = None
    model_config = {"from_attributes": True}


class CATCreate(BaseModel):
    employee_id: str
    tipo_acidente: str = "tipico"
    data_acidente: str
    local: str
    descricao: str = Field(..., min_length=10)
    gravidade: str = "leve"
    testemunhas: list[str] = []


class CATResponse(BaseModel):
    cat_id: str
    employee_id: str
    tipo: str
    data: str
    local: str
    gravidade: str
    status: str
    model_config = {"from_attributes": True}


class RiskCreate(BaseModel):
    posto_id: str
    categoria: str = Field(..., description="fisico|quimico|biologico|ergonomico|acidente")
    descricao: str
    nivel: str = "medio"
    fonte_geradora: str | None = None
    medidas_controle: list[str] | None = None
    epi_recomendado: list[str] | None = None


class RiskResponse(BaseModel):
    risk_id: str
    posto_id: str
    categoria: str
    descricao: str
    nivel: str
    status: str
    model_config = {"from_attributes": True}
