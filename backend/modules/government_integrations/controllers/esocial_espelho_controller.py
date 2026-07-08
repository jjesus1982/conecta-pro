"""
Controller — ESPELHO OFICIAL do eSocial (Missão D).

Endpoints:
- POST /esocial/espelho/sincronizar  → dispara task Celery (fila gov.esocial)
- GET  /esocial/espelho/resumo       → contagens por tipo/ano + anti-duplicidade
- GET  /esocial/espelho/timeline/{cpf} → linha do tempo do funcionário no governo

O sincronizar respeita o orçamento do GOVERNO: 10 acessos/dia nos webservices
de consulta identificadores + download, bloqueio dias 1-7 do mês. Pode haver
centenas de eventos — a enumeração continua nas próximas execuções (beat
semanal `esocial-espelho-sync`).
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_db

from ..services.esocial_espelho_service import resumo_espelho, timeline_cpf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/esocial/espelho", tags=["eSocial Espelho"])


class SincronizarEspelhoRequest(BaseModel):
    tipos: list[str] | None = Field(
        default=None,
        description="Tipos prioritários (default: S-2210, S-2220, S-2230, S-2240, S-2200, S-2299)",
    )
    periodo: str | None = Field(
        default=None, description="Período de RECEPÇÃO a enumerar: 'AAAA' ou 'AAAA-MM' (gera fila de janelas)"
    )
    cpfs: list[str] | None = Field(default=None, description="Restringe a estes CPFs (senão: fila existente)")
    max_acessos: int = Field(default=8, ge=1, le=10, description="Teto de acessos ao governo NESTA execução (dia=10)")


@router.post("/sincronizar", summary="Sincroniza o espelho oficial do eSocial (task Celery)")
async def sincronizar_espelho_endpoint(
    request: SincronizarEspelhoRequest,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Dispara a sincronização na fila gov.esocial (consulta+download são READ-ONLY no governo)."""
    from celery_app import app as celery_app

    task = celery_app.send_task(
        "government_integrations.tasks.espelho.sincronizar_espelho_esocial",
        kwargs={
            "tipos": request.tipos,
            "periodo": request.periodo,
            "cpfs": request.cpfs,
            "max_acessos": request.max_acessos,
        },
        queue="gov.esocial",
    )
    return {
        "success": True,
        "task_id": task.id,
        "mensagem": (
            "Sincronização do espelho disparada. Orçamento do governo: 10 acessos/dia, "
            "bloqueio dias 1-7 do mês — a enumeração continua nas próximas execuções."
        ),
    }


@router.get("/resumo", summary="Resumo do espelho (por tipo/ano) + anti-duplicidade")
async def resumo_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    return await resumo_espelho(db)


@router.get("/timeline/{cpf}", summary="Linha do tempo do funcionário no eSocial (eventos no governo)")
async def timeline_endpoint(
    cpf: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    eventos = await timeline_cpf(db, cpf)
    if not eventos:
        return {
            "cpf": cpf,
            "eventos": [],
            "mensagem": "Nenhum evento espelhado para este CPF (ainda). O espelho enumera aos poucos (10 acessos/dia).",
        }
    return {"cpf": cpf, "total": len(eventos), "eventos": eventos}
