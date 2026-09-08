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


@router.get("/institucional/cct")
async def get_cct_documento(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """CCT 2026 vigente para download."""
    try:
        cargos = (
            (
                await db.execute(
                    text(
                        "SELECT nome_cargo, cbo, salario_base, divisor_horas, escala_padrao "
                        "FROM cct_cargos ORDER BY nome_cargo"
                    )
                )
            )
            .mappings()
            .all()
        )

        return {
            "cct_vigente": "CCT 2026 SINDECOMPRESTS/SINDICOND-AM",
            "vigencia": {"inicio": "2026-01-01", "fim": "2026-12-31"},
            "sindicato_empregados": "SINDECOMPRESTS",
            "sindicato_patronal": "SINDICOND-AM",
            "cargos": [dict(c) for c in cargos],
            "total_cargos": len(cargos),
            "beneficios_obrigatorios": [
                {"tipo": "VA", "valor_diario": 22.00},
                {"tipo": "Cesta Basica", "valor_mensal": 18.00},
                {"tipo": "VT", "desconto_max": "4%"},
                {"tipo": "Plano Odontologico", "desconto_max": 9.00},
                {"tipo": "Seguro de Vida", "desconto_max": 2.00},
            ],
            "pasta_ged": "institucional/cct/",
            "documento_pdf": "CCT_SINDECOMPRESTS_2026.pdf",
        }
    except Exception as exc:
        logger.warning("Erro CCT documento: %s", exc)
        return {"cct_vigente": "CCT 2026", "cargos": []}


@router.get("/institucional/comunicados")
async def get_comunicados(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Comunicados institucionais do GED."""
    _ = db  # Disponivel para queries futuras
    return {
        "comunicados": [
            {
                "id": 1,
                "titulo": "CCT 2026 — Novos pisos salariais",
                "data": "2026-01-15",
                "tipo": "cct",
                "visivel_portal": True,
            },
            {
                "id": 2,
                "titulo": "Plano Odontologico — Adesao obrigatoria",
                "data": "2026-01-20",
                "tipo": "beneficio",
                "visivel_portal": True,
            },
        ],
        "total": 2,
    }
