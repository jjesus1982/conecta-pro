"""Controller para o Migrador de Contratos entre Empresas (Fase 3 Multi-Empresa)."""

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import CurrentActiveUser
from core.database import get_db
from modules.empresas.agents.contract_migrator import ContractMigratorAgent

router = APIRouter(prefix="/migrador", tags=["Migrador de Contratos"])
_agent = ContractMigratorAgent()


# ===================================================================
# REQUEST BODIES
# ===================================================================


class AnalisarContratoRequest(BaseModel):
    contrato_id: int
    tipo_servico: str
    empresa_atual_slug: str = "conecta_eletronica"
    receita_bruta_mes: float
    custo_direto_mes: float = 0.0
    rbt12_destino: float = 600000.0
    liminares_patrimonial: list[str] = []


class SimularMigracaoRequest(BaseModel):
    contrato_id: int
    tipo_servico: str
    empresa_atual_slug: str
    empresa_destino_slug: str
    receita_bruta_mes: float
    custo_direto_mes: float
    custo_indireto_mes: float = 0.0
    rbt12: float = 600000.0
    liminares: list[str] = []


class ExecutarMigracaoRequest(BaseModel):
    contrato_id: int | str = Field(..., description="UUID de contracts.id")
    empresa_origem_slug: str
    empresa_destino_slug: str
    data_migracao: date | None = None
    gerar_aditivo: bool = True


class GerarAditivoRequest(BaseModel):
    contrato_id: int
    empresa_origem: str
    empresa_destino: str
    cnpj_destino: str | None = None
    data_vigencia: date | None = None


class AnalisarLoteRequest(BaseModel):
    contratos: list[dict] = Field(..., description="Lista de {contrato_id, tipo_servico, receita_mes}")
    empresa_atual_slug: str = "conecta_eletronica"
    liminares_patrimonial: list[str] = []


# ===================================================================
# ENDPOINTS
# ===================================================================


@router.post("/executar")
async def executar_migracao(
    dados: ExecutarMigracaoRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
):
    """Executa a migração DE VERDADE: contracts.empresa_id + aditivo (ContractAddendum)."""
    resultado = await _agent.migrar_contrato(
        contrato_id=dados.contrato_id,
        empresa_origem_slug=dados.empresa_origem_slug,
        empresa_destino_slug=dados.empresa_destino_slug,
        data_migracao=dados.data_migracao,
        gerar_aditivo=dados.gerar_aditivo,
        db=db,
        usuario_id=str(getattr(current_user, "id", "")) or None,
    )
    return {
        "sucesso": resultado.sucesso,
        "mensagem": resultado.mensagem,
        "aditivo_gerado": resultado.aditivo_gerado,
        "aditivo_id": resultado.historico_id,
        "data_migracao": resultado.data_migracao.isoformat(),
    }


