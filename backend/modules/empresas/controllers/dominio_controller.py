"""
DominioController — Endpoints para exportação Domínio TOTVS
Inclui status da integração API (chave configurada pelo contador).
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from core.auth.dependencies import CurrentActiveUser

from ..agents.dominio_exporter import DominioExporterAgent

router = APIRouter(prefix="/empresas/dominio", tags=["Domínio TOTVS"])
agent = DominioExporterAgent()


class ExportarLancamentosRequest(BaseModel):
    empresa_slug: str
    periodo: str  # "YYYY-MM"
    lancamentos: list[dict] = []


class ExportarClientesRequest(BaseModel):
    empresa_slug: str
    clientes: list[dict] = []


class ExportarNfseRequest(BaseModel):
    empresa_slug: str
    periodo: str
    notas: list[dict] = []


@router.get("/status")
async def dominio_status(current_user: CurrentActiveUser):
    """Status da integração Domínio Sistemas — conectividade e modo de operação."""
    from modules.integrations.connectors.dominio import get_status

    return await get_status()


@router.get("/download/plano-contas/{empresa_slug}", response_class=PlainTextResponse)
def download_plano_contas(current_user: CurrentActiveUser, empresa_slug: str):
    resultado = agent.gerar_plano_contas(empresa_slug)
    if not resultado.get("sucesso"):
        raise HTTPException(status_code=500, detail=resultado.get("erro"))
    return PlainTextResponse(
        content=resultado["conteudo"],
        headers={"Content-Disposition": f"attachment; filename={resultado['nome_arquivo']}"},
    )
