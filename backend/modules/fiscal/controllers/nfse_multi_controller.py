"""
NFS-e Multi-Empresa Controller
Endpoints FastAPI prefix /api/v1/fiscal/nfse-multi
"""
# pylint: disable=unused-argument

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from core.auth.dependencies import get_current_user
from modules.fiscal.publishers import publish_nfs_emitida
from modules.fiscal.services.nfse_multi_empresa_service import (
    EMPRESAS_CONFIG,
    refresh_empresas_config,
    DadosNFSeMultiEmpresa,
    NfseMultiEmpresaService,
)

router = APIRouter(prefix="/nfse-multi", tags=["NFS-e Multi-Empresa"])
_service = NfseMultiEmpresaService()


# ─── Schemas ────────────────────────────────────────────────────────────────


class EmitirNFSeMultiRequest(BaseModel):
    tipo_servico: str = Field(..., example="vigilancia")
    descricao_servico: str = Field(
        ...,
        example="Servicos de vigilancia patrimonial - Competencia 03/2026",
    )
    valor_servico: float = Field(..., example=50000.00)
    tomador_cnpj_cpf: str = Field(..., example="12345678000195")
    tomador_razao_social: str = Field(..., example="Cliente Exemplo Ltda")
    tomador_email: str | None = None
    tomador_municipio_codigo: str = "1302603"
    empresa_slug: str | None = None
    competencia_ano: int = 2026
    competencia_mes: int = 3
    forcar_liminares: list[str] = Field(default_factory=list)


class CalcularTributosRequest(BaseModel):
    valor_servico: float = Field(..., example=50000.00)
    empresa_slug: str = Field(default="conecta_eletronica", example="conecta_eletronica")
    liminares: list[str] = Field(default_factory=list, example=["pis_cofins_zero"])


# ─── Endpoints ──────────────────────────────────────────────────────────────


@router.post(
    "/preparar",
    summary="Preparar NFS-e com empresa e liminares automaticas",
    response_model=dict[str, Any],
)
async def preparar_nfse_multi(
    dados: EmitirNFSeMultiRequest,
    current_user=Depends(get_current_user),
) -> dict[str, Any]:
    """
    Prepara NFS-e identificando empresa automaticamente e aplicando liminares.
    Retorna dados calculados e XML para revisão antes de transmitir.

    - **tipo_servico**: vigilancia, portaria_remota, cftv, limpeza, etc.
    - **forcar_liminares**: pis_cofins_zero, inss_nao_retido (para debug/teste)
    """
    dados_nfse = DadosNFSeMultiEmpresa(
        tipo_servico=dados.tipo_servico,
        descricao_servico=dados.descricao_servico,
        valor_servico=dados.valor_servico,
        tomador_cnpj_cpf=dados.tomador_cnpj_cpf,
        tomador_razao_social=dados.tomador_razao_social,
        tomador_email=dados.tomador_email,
        tomador_municipio_codigo=dados.tomador_municipio_codigo,
        empresa_slug=dados.empresa_slug,
        competencia_ano=dados.competencia_ano,
        competencia_mes=dados.competencia_mes,
        forcar_liminares=dados.forcar_liminares,
    )
    resultado = _service.preparar_dados_nfse(dados_nfse)

    # Publisher GEDEON Event Bus — NFS-e preparada
    if resultado.sucesso:
        try:
            import asyncio

            asyncio.create_task(
                publish_nfs_emitida(
                    nfs_id=getattr(resultado, "numero_nfse", "") or dados.tomador_cnpj_cpf or "",
                    numero=str(getattr(resultado, "numero_nfse", "") or ""),
                    valor=float(resultado.valor_servico or 0),
                    tomador=dados.tomador_razao_social or "",
                    competencia=f"{dados.competencia_ano}-{dados.competencia_mes:02d}",
                    cliente_id=dados.tomador_cnpj_cpf or None,
                    extra={
                        "empresa_emissora": resultado.empresa_emissora or "",
                        "tipo_servico": dados.tipo_servico or "",
                        "liminares": resultado.liminares_aplicadas,
                    },
                )
            )
        except Exception:
            pass

    return {
        "sucesso": resultado.sucesso,
        "empresa_emissora": resultado.empresa_emissora,
        "motivo_selecao_empresa": resultado.motivo_empresa,
        "liminares_aplicadas": resultado.liminares_aplicadas,
        "tributos": {
            "valor_servico": resultado.valor_servico,
            "pis": resultado.pis,
            "cofins": resultado.cofins,
            "iss": resultado.iss,
            "inss_retido": resultado.inss_retido,
            "valor_liquido": resultado.valor_liquido,
        },
        "xml_preview": resultado.xml_gerado,
        "mensagem": resultado.mensagem,
        "ambiente": resultado.ambiente,
    }


@router.get(
    "/identificar-empresa/{tipo_servico}",
    summary="Identificar empresa para tipo de servico",
    response_model=dict[str, Any],
)
async def identificar_empresa_nfse(
    tipo_servico: str,
    current_user=Depends(get_current_user),
) -> dict[str, Any]:
    """Identifica qual empresa deve emitir NFS-e para o tipo de serviço."""
    empresa = _service.identificar_empresa(tipo_servico)
    refresh_empresas_config()
    empresa_cfg = EMPRESAS_CONFIG.get(empresa, {})
    return {
        "tipo_servico": tipo_servico,
        "empresa_emissora": empresa,
        "regime": empresa_cfg.get("regime"),
        "tem_cnpj": empresa_cfg.get("cnpj") is not None,
        "liminares_previstas": empresa_cfg.get("liminares", []),
        "mensagem": f"Servicos de '{tipo_servico}' -> {empresa}",
    }


@router.post(
    "/calcular-tributos",
    summary="Calcular tributos NFS-e com liminares",
    response_model=dict[str, Any],
)
async def calcular_tributos_nfse(
    body: CalcularTributosRequest,
    current_user=Depends(get_current_user),
) -> dict[str, Any]:
    """Calcula tributos da NFS-e com liminares aplicadas."""
    return _service.calcular_tributos(
        valor_servico=body.valor_servico,
        empresa_slug=body.empresa_slug,
        liminares_ativas=body.liminares,
    )


@router.get(
    "/empresas",
    summary="Listar empresas disponíveis para emissão",
    response_model=dict[str, Any],
)
async def listar_empresas_nfse(
    current_user=Depends(get_current_user),
) -> dict[str, Any]:
    """Lista todas as empresas configuradas e seus status de emissão."""
    refresh_empresas_config()
    empresas_list = []
    for slug, cfg in EMPRESAS_CONFIG.items():
        empresas_list.append(
            {
                "slug": slug,
                "razao_social": cfg.get("razao_social"),
                "cnpj": cfg.get("cnpj"),
                "inscricao_municipal": cfg.get("inscricao_municipal"),
                "regime": cfg.get("regime"),
                "ambiente": cfg.get("ambiente"),
                "pode_emitir": cfg.get("cnpj") is not None,
                "liminares": cfg.get("liminares", []),
            }
        )
    return {
        "empresas": empresas_list,
        "total": len(empresas_list),
    }


@router.get(
    "/servicos",
    summary="Listar tipos de servico e empresa mapeada",
    response_model=dict[str, Any],
)
async def listar_servicos_mapeados(
    current_user=Depends(get_current_user),
) -> dict[str, Any]:
    """Retorna o mapeamento de tipos de serviço para empresas emissoras."""
    from modules.fiscal.services.nfse_multi_empresa_service import (
        SERVICOS_ELETRONICOS,
        SERVICOS_HUMANIZADOS,
    )

    return {
        "eletronica": {
            "empresa": "conecta_eletronica",
            "servicos": SERVICOS_ELETRONICOS,
        },
        "patrimonial": {
            "empresa": "conecta_patrimonial",
            "servicos": SERVICOS_HUMANIZADOS,
        },
    }
