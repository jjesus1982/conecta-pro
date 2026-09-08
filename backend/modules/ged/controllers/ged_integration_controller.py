"""
Controller de Integracao GED — Onboarding, SST, Portal, CCT.

Endpoints de documentos por colaborador, integrando:
- Onboarding checklist → docs admissionais
- SST → atestados, ASOs, CATs
- Portal → contracheques PDF
- CCT 2026 → convenção institucional
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ged-integration", tags=["GED - Integracao"])


# ═══════════════════════════════════════════════════
# FASE 2 — GED + ONBOARDING
# ═══════════════════════════════════════════════════


@router.get("/contracheques/{employee_id}")
async def get_contracheques(
    employee_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Historico de contracheques arquivados no GED."""
    try:
        emp = (
            (
                await db.execute(
                    text("SELECT nome, cargo, salario_base FROM employees WHERE id = :eid"), {"eid": employee_id}
                )
            )
            .mappings()
            .first()
        )

        if not emp:
            return {"employee_id": employee_id, "contracheques": []}

        emp_dict = dict(emp)

        docs = (
            (
                await db.execute(
                    text(
                        "SELECT id, competencia, ano, mes, path, tamanho_bytes, created_at "
                        "FROM ged_contracheques WHERE employee_id = :eid "
                        "ORDER BY ano DESC, mes DESC"
                    ),
                    {"eid": employee_id},
                )
            )
            .mappings()
            .all()
        )

        return {
            "employee_id": employee_id,
            "employee_name": emp_dict.get("nome", ""),
            "cargo": emp_dict.get("cargo", ""),
            "salario_base": str(emp_dict.get("salario_base", 0)),
            "contracheques": [dict(d) for d in docs],
            "total": len(docs),
            "pasta_ged": f"colaboradores/{employee_id}/contracheques/",
        }
    except Exception as exc:
        logger.warning("Erro contracheques GED: %s", exc)
        return {"employee_id": employee_id, "contracheques": []}


# ═══════════════════════════════════════════════════
# FASE 4 — GED + SST
# ═══════════════════════════════════════════════════


