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

# O router de ponto de `hr/time_tracking` é montado AQUI, e não lá dentro do
# `time_tracking_controller`, e a diferença é um prefixo repetido:
#
#   antes  /hr + /time-tracking (controller) + /time-tracking (sub-router) → 64 rotas em
#          `/hr/time-tracking/time-tracking/...`
#   agora  /hr + /time-tracking (sub-router)                               → 64 rotas em
#          `/hr/time-tracking/...`
#
# Medido antes de mexer, porque remover rota é mais fácil de fazer do que de desfazer:
#   · 15 dias de access log do nginx (30/07→13/08), 99.841 chamadas de API: **0** para o
#     caminho duplicado. A janela cobre a API de verdade — 8.282 chamadas `/api/` só hoje;
#   · nenhuma página em `app/**` importa o SDK gerado dessas rotas;
#   · colisão com as 2 rotas próprias do controller (`/employee/{id}/entries` e
#     `/from-operations`): ZERO, conferido rota a rota.
#
# NÃO removi as 64: `time_sheets` tem **170 linhas vivas** (169 `calculado`, 1 `fechado`,
# até hoje) e alimenta a tela de fechamento do DP, a assinatura do funcionário e os kits do
# GED. Elas leem por SQL direto, não por estas rotas — mas apagar a superfície de uma
# tabela viva porque ninguém a chamou em 15 dias seria confundir "sem uso" com "sem valor".
# As outras quatro tabelas do módulo (`time_entries`, `overtimes`, `time_justifications`,
# `work_schedules`) estão zeradas; essas sim são superfície sobre o vazio, e ficam
# declaradas no relatório em vez de escondidas atrás de um caminho que ninguém digita.
try:
    from modules.hr.time_tracking.controllers import router as _tt_router

    router.include_router(_tt_router)
    logger.debug("DP: _tt_router montado em /hr/time-tracking (sem prefixo duplicado)")
except ImportError as e:
    logger.warning("DP: falha ao montar _tt_router: %s", e)

# Mesma correção, mesmo motivo, para a folha: 43 rotas que nasciam em
# `/hr/payroll/payroll/...` passam a `/hr/payroll/...`. Ver a nota em `payroll_controller`.
try:
    from modules.hr.payroll_integration.controllers import router as _payroll_router

    router.include_router(_payroll_router)
    logger.debug("DP: _payroll_router montado em /hr/payroll (sem prefixo duplicado)")
except ImportError as e:
    logger.warning("DP: falha ao montar _payroll_router: %s", e)

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
        # NÃO devolve número quando a fonte falha. Este bloco chumbava
        # 52 funcionários / 41 ativos / 78,8% / 157 benefícios e ainda dizia `status: "ok"`
        # — quem consome não tinha como distinguir dado de invenção. Medido em 13/08/2026:
        # o real é 91 funcionários e 54 ativos. O fallback mentia por 13 pessoas, e mentiria
        # com mais folga a cada admissão, porque número chumbado não acompanha o cadastro.
        #
        # `status` passa a dizer a verdade e os campos vêm NULOS: tela que não sabe tratar
        # ausência mostra vazio, que é honesto; tela que mostra "78,8%" de um banco fora do ar
        # é mentira com aparência de relatório.
        logger.warning("hr_root_summary indisponível: %s", exc)
        return {
            "status": "indisponivel",
            "erro": "não foi possível ler os dados de RH agora",
            "resumo": {
                "total_funcionarios": None,
                "total_ativos": None,
                "total_inativos": None,
                "indice_atividade": None,
                "total_beneficios": None,
            },
            "cct": None,
        }
