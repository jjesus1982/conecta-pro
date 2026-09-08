"""
BookkeeperController — Endpoints escrituração contábil automática
"""

from fastapi import APIRouter
from pydantic import BaseModel

from core.auth.dependencies import CurrentActiveUser

from ..agents.bookkeeper_auto import BookkeeperAutoAgent

router = APIRouter(prefix="/empresas/contabilidade", tags=["Escrituração Contábil"])
agent = BookkeeperAutoAgent()


class LancamentosFolhaRequest(BaseModel):
    empresa_slug: str
    competencia: str
    funcionarios: list[dict] = []


class LancamentosImpostosRequest(BaseModel):
    empresa_slug: str
    competencia: str
    impostos: dict = {}
    regime: str = "lucro_real"


class ResumoContabilRequest(BaseModel):
    empresa_slug: str
    periodo: str
    receitas: float = 0
    custos_folha: float = 0
    impostos: float = 0
    despesas_admin: float = 0


@router.post("/resumo-mensal")
def resumo_mensal(current_user: CurrentActiveUser, req: ResumoContabilRequest):
    return agent.resumo_contabil_mensal(
        req.empresa_slug, req.periodo, req.receitas, req.custos_folha, req.impostos, req.despesas_admin
    )
