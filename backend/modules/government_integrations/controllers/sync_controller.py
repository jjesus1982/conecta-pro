"""
Controller REST para sincronização de dados governamentais.

Endpoints para:
- Execução manual de sincronizações
- Consulta de status e histórico
- Configuração de agendamentos
- Monitoramento de jobs ativos
"""

import logging
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db

from ..sync.sync_manager import SyncManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["Sincronização Governamental"])


# =============================================================================
# SCHEMAS
# =============================================================================


class ServicoEnum(StrEnum):
    """Serviços disponíveis para sincronização."""

    ESOCIAL = "esocial"
    RECEITA_FEDERAL = "receita_federal"
    NFE = "nfe"
    CTE = "cte"
    MDFE = "mdfe"
    NFSE = "nfse"
    SPED = "sped"
    FGTS = "fgts"
    INSS = "inss"
    GOVBR = "govbr"


class TipoSyncEnum(StrEnum):
    """Tipos de sincronização."""

    INCREMENTAL = "incremental"
    COMPLETA = "completa"


class SyncRequest(BaseModel):
    """Request para executar sincronização."""

    cnpj_empresa: str = Field(..., min_length=14, max_length=14, description="CNPJ da empresa (apenas números)")
    tipo_sync: TipoSyncEnum = Field(default=TipoSyncEnum.INCREMENTAL)
    data_inicial: date | None = Field(None, description="Data inicial para extração")
    data_final: date | None = Field(None, description="Data final para extração")
    parametros_extras: dict[str, Any] | None = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "cnpj_empresa": "12345678000190",
                "tipo_sync": "incremental",
                "data_inicial": "2024-01-01",
                "data_final": "2024-12-31",
            }
        }


class SyncAllRequest(BaseModel):
    """Request para sincronizar todos os serviços."""

    cnpj_empresa: str = Field(..., min_length=14, max_length=14)
    servicos: list[ServicoEnum] | None = Field(None, description="Serviços específicos (None = todos)")
    tipo_sync: TipoSyncEnum = Field(default=TipoSyncEnum.INCREMENTAL)


class AgendamentoRequest(BaseModel):
    """Request para configurar agendamento."""

    cnpj_empresa: str = Field(..., min_length=14, max_length=14)
    servico: ServicoEnum
    intervalo_minutos: int = Field(ge=5, le=1440, description="Intervalo entre execuções (5-1440 min)")
    ativo: bool = Field(default=True)
    horario_inicio: str | None = Field(None, description="Horário de início (HH:MM)")
    horario_fim: str | None = Field(None, description="Horário de fim (HH:MM)")


class ConfiguracaoEmpresaRequest(BaseModel):
    """Request para configurar integração de empresa."""

    cnpj_empresa: str = Field(..., min_length=14, max_length=14)
    certificate_id: str | None = None
    govbr_cpf: str | None = None
    govbr_token: str | None = None
    uf_empresa: str | None = Field(None, max_length=2)
    codigo_municipio: str | None = None
    ambiente: str = Field(default="producao", pattern="^(producao|homologacao)$")


class SyncResultResponse(BaseModel):
    """Response com resultado de sincronização."""

    sucesso: bool
    job_id: str | None = None
    servico: str
    registros_processados: int = 0
    registros_novos: int = 0
    registros_atualizados: int = 0
    registros_erro: int = 0
    mensagem: str = ""
    duracao_segundos: float = 0
    erros: list[dict[str, Any]] = []

    class Config:
        from_attributes = True


class JobStatusResponse(BaseModel):
    """Response com status de job."""

    job_id: str
    servico: str
    cnpj: str
    status: str
    inicio: datetime
    fim: datetime | None = None
    resultado: SyncResultResponse | None = None


class HistoricoResponse(BaseModel):
    """Response com histórico de sincronizações."""

    id: str
    cnpj_empresa: str
    servico: str
    tipo_sync: str
    status: str
    inicio_execucao: datetime
    fim_execucao: datetime | None
    registros_processados: int
    registros_novos: int
    registros_erro: int
    mensagem: str | None
    duracao_segundos: float | None


class StatusSyncResponse(BaseModel):
    """Response com status geral de sincronização."""

    cnpj_empresa: str
    servicos: dict[str, dict[str, Any]]
    jobs_ativos: int
    ultima_sincronizacao: datetime | None


# =============================================================================
# DEPENDENCY
# =============================================================================

_sync_manager: SyncManager | None = None


def get_sync_manager(db: AsyncSession = Depends(get_db)) -> SyncManager:  # type: ignore[arg-type]
    """Obtém instância do SyncManager."""
    global _sync_manager
    if _sync_manager is None:
        _sync_manager = SyncManager(db)
    else:
        _sync_manager.db = db
    return _sync_manager


# =============================================================================
# ENDPOINTS DE EXECUÇÃO
# =============================================================================


# =============================================================================
# ENDPOINTS DE CONSULTA
# =============================================================================


# =============================================================================
# ENDPOINTS DE CONFIGURAÇÃO
# =============================================================================


# =============================================================================
# ENDPOINTS DE DADOS SINCRONIZADOS
# =============================================================================


