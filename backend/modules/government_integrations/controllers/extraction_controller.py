"""
Controller de Extração de Dados Governamentais.

Endpoints para iniciar e gerenciar extrações.
"""

import logging
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator


from ..extractors.orchestrator import (
    TipoServico,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/extracao", tags=["Extração Governamental"])


# ============================================================================
# Schemas
# ============================================================================


class IniciarExtracaoRequest(BaseModel):
    """Requisição para iniciar extração."""

    servicos: list[str] | None = Field(
        None, description="Serviços a sincronizar. Se vazio, sincroniza todos.", example=["sefaz_nfe", "esocial"]
    )
    cnpjs: list[str] | None = Field(
        None, description="CNPJs específicos. Se vazio, usa todos do tenant.", example=["12345678000100"]
    )
    ufs: list[str] | None = Field(None, description="UFs para consulta SEFAZ", example=["AM", "SP"])
    data_inicio: datetime | None = Field(None, description="Data inicial do período")
    data_fim: datetime | None = Field(None, description="Data final do período")
    dias: int = Field(30, ge=1, le=365, description="Dias para trás (se data_inicio não informada)")
    modo_incremental: bool = Field(True, description="Se True, busca apenas novos documentos")
    executar_async: bool = Field(True, description="Se True, executa em background via Celery")

    @field_validator("servicos")
    @classmethod
    def validar_servicos(cls, v):
        if v:
            validos = [t.value for t in TipoServico]
            for s in v:
                if s not in validos:
                    raise ValueError(f"Serviço inválido: {s}. Válidos: {validos}")
        return v


class ExtracaoResponse(BaseModel):
    """Resposta de extração."""

    id: str
    status: str
    servicos: list[str]
    iniciado_em: datetime
    modo: str
    mensagem: str


class StatusExtracaoResponse(BaseModel):
    """Status de uma extração em andamento."""

    id: str
    status: str
    progresso: float
    documentos_processados: int
    documentos_novos: int
    documentos_erro: int
    servicos_concluidos: list[str]
    servicos_pendentes: list[str]
    erros: list[str]
    iniciado_em: datetime
    estimativa_conclusao: datetime | None = None


class HistoricoExtracaoResponse(BaseModel):
    """Histórico de extrações."""

    id: str
    tenant_id: str
    servicos: list[str]
    status: str
    documentos_processados: int
    documentos_novos: int
    documentos_erro: int
    iniciado_em: datetime
    finalizado_em: datetime | None
    duracao_segundos: float | None
    usuario_id: str | None


# ============================================================================
# Endpoints
# ============================================================================


# ============================================================================
# Endpoints de Sincronização Rápida
# ============================================================================


