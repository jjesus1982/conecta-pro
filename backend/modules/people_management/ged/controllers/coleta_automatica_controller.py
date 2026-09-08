"""D4 — Coleta Automática: GET/POST config, POST run, GET history."""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.cache.redis import get_redis
from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/coleta-automatica", tags=["GED - Coleta Automatica"])

# Lock Redis: evita duplo-run simultâneo
RUNNING_LOCK_KEY = "ged:coleta:running"
RUNNING_LOCK_TTL = 600  # 10 min máximo


class ColetaConfigUpdate(BaseModel):
    enabled: bool
    cron_expr: str


class ColetaRunRequest(BaseModel):
    mes_ref: str | None = None
    force_resync: bool = False


@router.get("")
async def get_config(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Retorna configuração atual da coleta automática."""
    from modules.people_management.ged.services.coleta_automatica_service import (
        ColetaAutomaticaService,
    )

    svc = ColetaAutomaticaService(db)
    cfg = await svc.get_config()
    return {
        "enabled": cfg.enabled,
        "cron_expr": cfg.cron_expr,
        "timezone": cfg.timezone,
        "last_run": cfg.last_run.isoformat() if cfg.last_run else None,
        "last_status": cfg.last_status,
    }


@router.post("")
async def update_config(
    body: ColetaConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Atualiza enabled e cron_expr da coleta automática."""
    from croniter import croniter

    if not croniter.is_valid(body.cron_expr):
        raise HTTPException(status_code=400, detail="cron_expr inválida")

    from modules.people_management.ged.services.coleta_automatica_service import (
        ColetaAutomaticaService,
    )

    svc = ColetaAutomaticaService(db)
    await svc.update_config(
        enabled=body.enabled,
        cron_expr=body.cron_expr,
        updated_by=getattr(current_user, "email", "unknown"),
    )
    return {"ok": True, "cron_expr": body.cron_expr, "enabled": body.enabled}


@router.post("/run", status_code=202)
async def run_now(
    body: ColetaRunRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Dispara coleta manual imediata (background). Idempotente via lock Redis."""
    redis = await get_redis()

    # Verificar lock
    if await redis.get(RUNNING_LOCK_KEY):
        raise HTTPException(
            status_code=409,
            detail="Coleta já em execução. Aguarde a conclusão ou verifique /coleta-automatica/history.",
        )

    # Setar lock
    await redis.set(RUNNING_LOCK_KEY, "1", ex=RUNNING_LOCK_TTL)

    task_id = str(uuid.uuid4())
    triggered_by = getattr(current_user, "email", "unknown")
    started_at = datetime.now(UTC)

    async def _run() -> None:
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from core.config.settings import get_settings
        from modules.people_management.ged.services.coleta_automatica_service import (
            ColetaAutomaticaService,
        )

        settings = get_settings()
        try:
            engine = create_async_engine(settings.database_url)
            _session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            async with _session_factory() as session:
                svc = ColetaAutomaticaService(session)
                await svc.executar(
                    run_type="manual",
                    triggered_by=triggered_by,
                    mes_ref=body.mes_ref,
                    force_resync=body.force_resync,
                )
        except Exception as e:
            logger.error("Background coleta falhou: %s", e)
        finally:
            redis_inner = await get_redis()
            await redis_inner.delete(RUNNING_LOCK_KEY)

    background_tasks.add_task(_run)

    return {
        "task_id": task_id,
        "status": "started",
        "started_at": started_at.isoformat(),
        "message": "Coleta iniciada em background. Acompanhe em /coleta-automatica/history",
    }


RUNNING_LOCK_KEY_CNDS = "ged:certidoes:running"
RUNNING_LOCK_TTL_CNDS = 300  # 5 min


@router.get("/history")
async def get_history(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Retorna histórico de execuções paginado (default 20, máx 100)."""
    limit = min(limit, 100)

    from modules.people_management.ged.services.coleta_automatica_service import (
        ColetaAutomaticaService,
    )

    svc = ColetaAutomaticaService(db)
    logs = await svc.get_history(limit=limit)

    return [
        {
            "id": str(log.id),
            "run_at": log.run_at.isoformat() if log.run_at else None,
            "run_type": log.run_type,
            "status": log.status,
            "duration_ms": log.duration_ms,
            "sync_novos": log.sync_novos,
            "kits_assembled": log.kits_assembled,
            "onvio_matched": log.onvio_matched,
            "certidoes_atualizadas": log.certidoes_atualizadas,
            "alertas_disparados": log.alertas_disparados,
            "triggered_by": log.triggered_by,
            "erros": log.erros,
        }
        for log in logs
    ]
