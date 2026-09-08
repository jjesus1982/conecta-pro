"""
StatementsController — DRE, Balanço Patrimonial e DFC
"""

from fastapi import APIRouter
from pydantic import BaseModel


from ..agents.financial_statements import FinancialStatementsAgent

router = APIRouter(prefix="/empresas/demonstrativos", tags=["Demonstrativos Financeiros"])
agent = FinancialStatementsAgent()


class DRERequest(BaseModel):
    empresa_slug: str
    periodo: str
    dados: dict
    regime: str = "lucro_real"


class BalancoRequest(BaseModel):
    empresa_slug: str
    data_base: str
    dados: dict


class DFCRequest(BaseModel):
    empresa_slug: str
    periodo: str
    dados: dict


class ConsolidadoRequest(BaseModel):
    periodo: str
    empresas: list[dict]


