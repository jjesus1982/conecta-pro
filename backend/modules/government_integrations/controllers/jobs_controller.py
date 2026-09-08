"""
Controller para gerenciamento de Jobs de Sincronizacao Governamental.

Endpoints:
- POST /jobs/registrar-todos - Registra todos os jobs para o tenant
- GET /jobs - Lista jobs do tenant
- GET /jobs/status - Status geral da sincronizacao
- POST /jobs/{tipo}/executar - Executa job imediatamente
- PATCH /jobs/{id} - Atualiza configuracao do job
- POST /jobs/{tipo}/pausar - Pausa job
- POST /jobs/{tipo}/retomar - Retoma job pausado
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from modules.government_integrations.jobs import (
    SyncJobType,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["Government Sync Jobs"])


# =========================================================================
# SCHEMAS
# =========================================================================


class JobRegistroResponse(BaseModel):
    """Resposta do registro de jobs."""

    sucesso: list[str]
    erros: list[dict]
    total: int


class JobInfo(BaseModel):
    """Informacoes de um job."""

    id: str
    nome: str
    tipo: str
    cron: str
    status: str
    ultima_execucao: str | None
    proxima_execucao: str | None
    total_execucoes: int = 0
    falhas: int = 0
    tags: list[str] = []


class JobListResponse(BaseModel):
    """Lista de jobs."""

    jobs: list[JobInfo]
    total: int


class JobStatusResponse(BaseModel):
    """Status da sincronizacao."""

    federal: list[dict]
    estadual: list[dict]
    municipal: list[dict]
    resumo: dict


class JobUpdateRequest(BaseModel):
    """Requisicao de atualizacao de job."""

    cron_expression: str | None = Field(None, description="Nova expressao cron")
    ativo: bool | None = Field(None, description="Ativar/desativar job")
    prioridade: int | None = Field(None, ge=1, le=10, description="Prioridade (1-10)")


class JobExecResponse(BaseModel):
    """Resposta de execucao de job."""

    sucesso: bool
    mensagem: str
    job_id: str | None = None


class JobConfigInfo(BaseModel):
    """Configuracao disponivel de job."""

    tipo: str
    nome: str
    descricao: str
    cron_padrao: str
    prioridade: int
    tags: list[str]


# =========================================================================
# ENDPOINTS
# =========================================================================


# =========================================================================
# HELPERS
# =========================================================================


def _extrair_tipo_job(job: dict) -> str:
    """Extrai tipo do job a partir das tags ou nome."""
    nome = job.get("nome", "").lower()

    for job_type in SyncJobType:
        if job_type.value in nome or job_type.value.replace("_", " ") in nome:
            return job_type.value

    return "desconhecido"
