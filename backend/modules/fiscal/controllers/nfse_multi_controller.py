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


