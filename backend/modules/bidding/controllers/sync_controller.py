"""
Controller de Sincronizacao - Licitacoes
=========================================
Endpoints para disparar e monitorar sincronizacoes com portais
publicos (PNCP, ComprasNet, etc.) via Celery tasks.
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from modules.bidding.models.sync_job import BiddingSyncJob

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["Licitacoes - Sincronizacao"])


# ============================================================
# Schemas
# ============================================================


class PNCPSyncRequest(BaseModel):
    uf: str = Field(default="AM", max_length=2)
    keywords: list[str] | None = Field(default=None)


class PrecosSyncRequest(BaseModel):
    portal: str = Field(default="pncp")
    uf: str = Field(default="AM", max_length=2)


class SyncTriggerResponse(BaseModel):
    task_id: str
    status: str = "queued"
    message: str


# ============================================================
# Helpers
# ============================================================


def _job_to_dict(job: BiddingSyncJob) -> dict:
    return {
        "id": str(job.id),
        "portal": job.portal,
        "tipo": getattr(job, "tipo", None),
        "status": job.status,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "registros_processados": getattr(job, "registros_processados", 0),
        "registros_novos": getattr(job, "registros_novos", 0),
        "registros_atualizados": getattr(job, "registros_atualizados", 0),
        "erros": getattr(job, "erros", []),
        "filtros_utilizados": getattr(job, "filtros_utilizados", {}),
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


def _send_celery_task(task_name: str, **kwargs) -> str:
    try:
        from celery_app import app as celery_app

        result = celery_app.send_task(task_name, kwargs=kwargs)
        return result.id
    except Exception as e:
        logger.warning(f"Celery indisponivel: {e}")
        import uuid

        return f"local-{uuid.uuid4().hex[:12]}"


# ============================================================
# POST /sync/pncp/trigger
# ============================================================


# ============================================================
# GET /sync/jobs
# ============================================================


# ============================================================
# GET /sync/jobs/{job_id}
# ============================================================


# ============================================================
# POST /sync/precos/trigger
# ============================================================


# ============================================================
# GET /sync/status
# ============================================================


