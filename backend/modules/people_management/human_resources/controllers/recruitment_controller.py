"""
Re-exportacao dos controllers de Recrutamento.

Inclui todos os routers de recrutamento (candidatos, vagas,
aplicacoes, entrevistas) sob o prefixo /human-resources/recruitment.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recruitment", tags=["RH - Recrutamento"])


@router.get("")
async def recruitment_overview(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Agregado honesto de recrutamento: contagens reais das tabelas.

    Antes este caminho respondia 404 (so as sub-rotas existiam).
    """

    async def _count(sql: str) -> int | None:
        try:
            return (await db.execute(text(sql))).scalar() or 0
        except Exception as exc:  # tabela ausente -> indisponivel, nunca inventar
            logger.warning("Recrutamento overview: %s", exc)
            return None

    candidatos = await _count("SELECT count(*) FROM candidates")
    vagas = await _count("SELECT count(*) FROM job_positions")
    vagas_abertas = await _count("SELECT count(*) FROM job_positions WHERE status = 'aberta'")
    aplicacoes = await _count("SELECT count(*) FROM applications")
    entrevistas = await _count("SELECT count(*) FROM interviews")

    return {
        "candidatos": candidatos,
        "vagas": vagas,
        "vagas_abertas": vagas_abertas,
        "aplicacoes": aplicacoes,
        "entrevistas": entrevistas,
        "indisponiveis": [
            k
            for k, v in {
                "candidatos": candidatos,
                "vagas": vagas,
                "aplicacoes": aplicacoes,
                "entrevistas": entrevistas,
            }.items()
            if v is None
        ],
        "sub_rotas": [
            "/recruitment/candidates",
            "/recruitment/job-positions",
            "/recruitment/applications",
            "/recruitment/interviews",
        ],
    }

try:
    from modules.recruitment.controllers.candidate_controller import (
        router as candidate_router,
    )

    router.include_router(candidate_router)
except ImportError:
    logger.warning("Modulo recruitment/candidate_controller nao disponivel para re-export.")

try:
    from modules.recruitment.controllers.job_position_controller import (
        router as job_position_router,
    )

    router.include_router(job_position_router)
except ImportError:
    logger.warning("Modulo recruitment/job_position_controller nao disponivel para re-export.")

try:
    from modules.recruitment.controllers.application_controller import (
        router as application_router,
    )

    router.include_router(application_router)
except ImportError:
    logger.warning("Modulo recruitment/application_controller nao disponivel para re-export.")

try:
    from modules.recruitment.controllers.interview_controller import (
        router as interview_router,
    )

    router.include_router(interview_router)
except ImportError:
    logger.warning("Modulo recruitment/interview_controller nao disponivel para re-export.")
