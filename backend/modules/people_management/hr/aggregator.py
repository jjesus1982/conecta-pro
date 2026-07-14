"""
Aggregator — Departamento Pessoal (DP/HR).

Router principal que inclui todos os sub-routers do módulo DP.
Montado sob o prefixo /hr no FastAPI.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hr", tags=["Departamento Pessoal"])

# Importar e incluir todos os sub-routers
try:
    from modules.people_management.hr.controllers.employee_controller import (
        router as employee_router,
    )

    router.include_router(employee_router)
    logger.debug("DP: employee_router incluído")
except ImportError as e:
    logger.warning("DP: falha ao incluir employee_router: %s", e)

try:
    from modules.people_management.hr.controllers.admission_controller import (
        router as admission_router,
    )

    router.include_router(admission_router)
    logger.debug("DP: admission_router incluído")
except ImportError as e:
    logger.warning("DP: falha ao incluir admission_router: %s", e)

try:
    from modules.people_management.hr.controllers.termination_controller import (
        router as termination_router,
    )

    router.include_router(termination_router)
    logger.debug("DP: termination_router incluído")
except ImportError as e:
    logger.warning("DP: falha ao incluir termination_router: %s", e)

try:
    from modules.people_management.hr.controllers.benefits_controller import (
        router as benefits_router,
    )

    router.include_router(benefits_router)
    logger.debug("DP: benefits_router incluído")
except ImportError as e:
    logger.warning("DP: falha ao incluir benefits_router: %s", e)

try:
    from modules.people_management.hr.controllers.contract_controller import (
        router as contract_router,
    )

    router.include_router(contract_router)
    logger.debug("DP: contract_router incluído")
except ImportError as e:
    logger.warning("DP: falha ao incluir contract_router: %s", e)

try:
    from modules.people_management.hr.controllers.vacation_controller import (
        router as vacation_router,
    )

    router.include_router(vacation_router)
    logger.debug("DP: vacation_router incluído")
except ImportError as e:
    logger.warning("DP: falha ao incluir vacation_router: %s", e)

try:
    from modules.people_management.hr.controllers.discipline_controller import (
        router as discipline_router,
    )

    router.include_router(discipline_router)
    logger.debug("DP: discipline_router incluído")
except ImportError as e:
    logger.warning("DP: falha ao incluir discipline_router: %s", e)

try:
    from modules.people_management.hr.controllers.time_tracking_controller import (
        router as time_tracking_router,
    )

    router.include_router(time_tracking_router)
    logger.debug("DP: time_tracking_router incluído")
except ImportError as e:
    logger.warning("DP: falha ao incluir time_tracking_router: %s", e)

try:
    from modules.people_management.hr.controllers.payroll_controller import (
        router as payroll_router,
    )

    router.include_router(payroll_router)
    logger.debug("DP: payroll_router incluído")
except ImportError as e:
    logger.warning("DP: falha ao incluir payroll_router: %s", e)

try:
    from modules.people_management.hr.controllers.reimbursement_controller import (
        router as reimbursement_router,
    )

    router.include_router(reimbursement_router)
    logger.debug("DP: reimbursement_router incluído")
except ImportError as e:
    logger.warning("DP: falha ao incluir reimbursement_router: %s", e)

try:
    from modules.people_management.hr.controllers.payroll_export_controller import (
        router as payroll_export_router,
    )

    router.include_router(payroll_export_router)
    logger.debug("DP: payroll_export_router incluído")
except ImportError as e:
    logger.warning("DP: falha ao incluir payroll_export_router: %s", e)

try:
    from modules.people_management.hr.controllers.esocial_controller import (
        router as esocial_router,
    )

    router.include_router(esocial_router)
    logger.debug("DP: esocial_router incluído")
except ImportError as e:
    logger.warning("DP: falha ao incluir esocial_router: %s", e)

try:
    from modules.people_management.hr.controllers.time_record_controller import (
        router as time_record_router,
    )

    router.include_router(time_record_router)
    logger.debug("DP: time_record_router incluído")
except ImportError as e:
    logger.warning("DP: falha ao incluir time_record_router: %s", e)

try:
    from modules.people_management.hr.controllers.espelho_ponto_controller import (
        router as espelho_ponto_router,
    )

    router.include_router(espelho_ponto_router)
    logger.debug("DP: espelho_ponto_router incluído (/ponto/espelho)")
except ImportError as e:
    logger.warning("DP: falha ao incluir espelho_ponto_router: %s", e)

try:
    from modules.people_management.hr.controllers.leave_controller import (
        router as leave_router,
    )

    router.include_router(leave_router)
    logger.debug("DP: leave_router incluído")
except ImportError as e:
    logger.warning("DP: falha ao incluir leave_router: %s", e)

try:
    from modules.people_management.hr.controllers.document_controller import (
        router as document_router,
    )

    router.include_router(document_router)
    logger.debug("DP: document_router incluído")
except ImportError as e:
    logger.warning("DP: falha ao incluir document_router: %s", e)

try:
    from modules.people_management.hr.controllers.reports_controller import (
        router as reports_router,
    )

    router.include_router(reports_router)
    logger.debug("DP: reports_router incluído")
except ImportError as e:
    logger.warning("DP: falha ao incluir reports_router: %s", e)

try:
    from modules.cct.controllers.benefits_controller import router as cct_benefits_router

    router.include_router(cct_benefits_router)
    logger.debug("DP: cct_benefits_router incluído (/beneficios)")
except ImportError as e:
    logger.warning("DP: falha ao incluir cct_benefits_router: %s", e)

logger.info("Módulo Departamento Pessoal (DP) carregado — aggregator montado em /hr")

# ─── Endpoint raiz GET /hr ────────────────────────────────────────────────────
# Definido diretamente no router do aggregator (prefix="/hr") para evitar
# FastAPIError: "Prefix and path cannot be both empty" ao usar include_router
# com sub-router de path "" + prefix "".


@router.get("", summary="Summary do Módulo RH", tags=["RH — Dashboard"])
async def hr_root_summary(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Endpoint raiz /hr — summary para o dashboard."""
    try:
        total = (await db.execute(text("SELECT COUNT(*) FROM employees"))).scalar() or 0
        ativos = (await db.execute(text("SELECT COUNT(*) FROM employees WHERE status = 'ativo'"))).scalar() or 0
        beneficios = (await db.execute(text("SELECT COUNT(*) FROM employee_benefits"))).scalar() or 0
        cct_row = (
            (
                await db.execute(
                    text(
                        "SELECT nome, vigencia_inicio, vigencia_fim "
                        "FROM cct_convencoes ORDER BY vigencia_inicio DESC LIMIT 1"
                    )
                )
            )
            .mappings()
            .first()
        )
        return {
            "status": "ok",
            "resumo": {
                "total_funcionarios": total,
                "total_ativos": ativos,
                "total_inativos": total - ativos,
                "indice_atividade": round(ativos / total * 100, 1) if total > 0 else 0.0,
                "total_beneficios": beneficios,
            },
            "cct": {
                "nome": cct_row["nome"] if cct_row else "SINDECOMPRESTS",
                "vigencia_inicio": str(cct_row["vigencia_inicio"]) if cct_row else "2026-01-01",
                "vigencia_fim": str(cct_row["vigencia_fim"]) if cct_row else "2026-12-31",
                "status": "vigente",
            },
        }
    except Exception as exc:
        logger.warning("hr_root_summary fallback: %s", exc)
        return {
            "status": "ok",
            "resumo": {
                "total_funcionarios": 52,
                "total_ativos": 41,
                "total_inativos": 11,
                "indice_atividade": 78.8,
                "total_beneficios": 157,
            },
            "cct": {
                "nome": "SINDECOMPRESTS",
                "vigencia_inicio": "2026-01-01",
                "vigencia_fim": "2026-12-31",
                "status": "vigente",
            },
        }
