"""
Controller de Integracao ERP - Licitacoes
=========================================
Endpoints para integracao entre modulos:
  Licitacao -> Operacional -> Financeiro
"""

import logging
from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/erp", tags=["Licitacoes - Integracao ERP"])


# ------------------------------------------------------------------ #
#  Schemas de request                                                #
# ------------------------------------------------------------------ #


class PostoConfig(BaseModel):
    """Configuracao de posto para conversao."""

    name: str = Field(..., description="Nome do posto")
    post_type: str = Field(default="porteiro", description="Tipo: porteiro, controlador de acesso, etc.")
    shift_type: str = Field(default="diurno", description="Turno: diurno, noturno, 12x36, etc.")
    headcount: int = Field(default=1, ge=1, description="Quantidade de funcionarios necessarios")
    address: str | None = Field(default=None, description="Endereco do posto")
    city: str | None = Field(default=None, description="Cidade")
    state: str | None = Field(default=None, description="UF")
    hourly_rate: float | None = Field(default=None, description="Valor hora")
    monthly_cost: float | None = Field(default=None, description="Custo mensal")
    requires_armed: bool = Field(default=False, description="Exige armamento")
    requires_vehicle: bool = Field(default=False, description="Exige veiculo")


class ConverterRequest(BaseModel):
    """Request para converter contrato em entidades operacionais."""

    postos: list[PostoConfig] | None = Field(
        default=None,
        description="Lista de postos a criar. Se vazio, cria posto generico.",
    )


class MedicaoRequest(BaseModel):
    """Request para gerar medicao."""

    competencia: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}$",
        description="Competencia no formato YYYY-MM",
    )
    periodo_inicio: date = Field(..., description="Data inicio do periodo")
    periodo_fim: date = Field(..., description="Data fim do periodo")


# ------------------------------------------------------------------ #
#  Endpoints                                                         #
# ------------------------------------------------------------------ #


