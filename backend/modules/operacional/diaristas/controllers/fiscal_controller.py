"""
Controller Fiscal para Diaristas.

Fornece endpoints para:
- Cálculo de retenções
- Geração de RPA
- Consulta de documentos
- Relatórios fiscais
"""

from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field


router = APIRouter()


# =============================================================================
# SCHEMAS
# =============================================================================


class CalculoRetencoesRequest(BaseModel):
    """Request para calcular retenções."""

    valor_bruto: Decimal = Field(..., gt=0, description="Valor bruto do serviço")
    dependentes: int = Field(0, ge=0, description="Número de dependentes (IRRF)")
    aliquota_iss: Decimal | None = Field(None, ge=0, le=5, description="Alíquota ISS (%)")


class RetencaoResponse(BaseModel):
    """Response de uma retenção."""

    base_calculo: float
    aliquota: float
    valor: float


class RetencoesResponse(BaseModel):
    """Response completo de retenções."""

    valor_bruto: float
    inss: RetencaoResponse
    irrf: dict[str, Any]
    iss: RetencaoResponse
    total_retencoes: float
    valor_liquido: float


class GerarRPARequest(BaseModel):
    """Request para gerar RPA."""

    diarist_id: UUID
    payment_id: UUID | None = None
    valor_bruto: Decimal | None = Field(None, gt=0)
    competencia: str | None = Field(None, pattern=r"^\d{4}-\d{2}$")
    descricao_servico: str = Field("Prestação de serviços de limpeza e conservação", max_length=500)
    codigo_servico: str = Field("7.10", max_length=20)
    dependentes: int = Field(0, ge=0)
    aliquota_iss: Decimal | None = Field(None)
    tomador_cnpj: str | None = Field(None, max_length=18)
    tomador_razao_social: str | None = Field(None, max_length=200)


class DocumentoFiscalResponse(BaseModel):
    """Response de documento fiscal."""

    id: str
    numero: str
    tipo: str
    status: str
    competencia: str
    data_emissao: str
    valor_bruto: float
    valor_inss: float
    valor_iss: float
    valor_irrf: float
    valor_liquido: float
    prestador_nome: str
    prestador_cpf: str


class RelatorioRetencoesResponse(BaseModel):
    """Response de relatório de retenções."""

    periodo: dict[str, str]
    totais: dict[str, float]
    documentos: int


# =============================================================================
# ENDPOINTS - CÁLCULOS
# =============================================================================


# =============================================================================
# ENDPOINTS - DOCUMENTOS
# =============================================================================


# =============================================================================
# ENDPOINTS - RELATÓRIOS
# =============================================================================


# =============================================================================
# ENDPOINTS - TABELAS
# =============================================================================


