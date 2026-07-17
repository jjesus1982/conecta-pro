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


@router.post("/analisar")
async def analisar_contrato(dados: AnalisarContratoRequest, current_user: CurrentActiveUser):
    """Analisa se contrato deve ser migrado e calcula impacto tributário."""
    resultado = _agent.analisar_contrato(**dados.dict())
    return {
        "contrato_id": resultado.contrato_id,
        "tipo_servico": resultado.tipo_servico,
        "empresa_atual": resultado.empresa_atual_slug,
        "empresa_destino": resultado.empresa_destino_slug,
        "deve_migrar": resultado.deve_migrar,
        "motivo": resultado.motivo,
        "impacto_financeiro": {
            "imposto_atual_mes": resultado.imposto_atual_mes,
            "imposto_destino_mes": resultado.imposto_destino_mes,
            "economia_mensal": resultado.economia_mensal,
            "economia_anual": resultado.economia_anual,
        },
        "pendencias": resultado.pendencias,
        "pode_migrar_imediatamente": resultado.pode_migrar_imediatamente,
    }


@router.post("/simular")
async def simular_migracao(dados: SimularMigracaoRequest, current_user: CurrentActiveUser):
    """Simula impacto completo da migração antes de executar."""
    resultado = _agent.simular_migracao(**dados.dict())
    return {
        "contrato_id": resultado.contrato_id,
        "empresa_destino": resultado.empresa_destino_slug,
        "receita_bruta_mes": resultado.receita_bruta_mes,
        "impostos": {
            "origem_mes": resultado.impostos_origem_mes,
            "destino_mes": resultado.impostos_destino_mes,
            "economia_mes": resultado.economia_impostos_mes,
            "economia_anual": resultado.economia_impostos_anual,
        },
        "margem": {
            "origem_pct": resultado.margem_origem,
            "destino_pct": resultado.margem_destino,
            "ganho_pct": resultado.ganho_margem,
        },
        "vale_migrar": resultado.vale_migrar,
        "recomendacao": resultado.recomendacao,
        "liminares_aplicadas": resultado.liminares_aplicadas,
    }


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


@router.post("/aditivo")
async def gerar_aditivo(dados: GerarAditivoRequest, current_user: CurrentActiveUser):
    """Gera texto do aditivo contratual para migração."""
    texto = _agent.gerar_texto_aditivo(**dados.dict())
    return {"aditivo_texto": texto, "formato": "texto_simples"}


@router.post("/analisar-lote")
async def analisar_lote(dados: AnalisarLoteRequest, current_user: CurrentActiveUser):
    """Analisa múltiplos contratos de uma vez."""
    return _agent.analisar_lote_por_tipo(
        contratos=dados.contratos,
        empresa_atual_slug=dados.empresa_atual_slug,
        liminares_patrimonial=dados.liminares_patrimonial,
    )


@router.get("/sugerir/{tipo_servico}")
async def sugerir_empresa(tipo_servico: str, current_user: CurrentActiveUser):
    """Retorna qual empresa deve faturar o tipo de serviço."""
    return _agent.classificar_servico(tipo_servico)
