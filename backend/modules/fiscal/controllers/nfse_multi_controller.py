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


