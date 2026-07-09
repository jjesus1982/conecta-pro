"""
CCT 2026 SINDECOMPRESTS — Controller
Convenção Coletiva de Trabalho para empresas de segurança patrimonial.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_async_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cct", tags=["CCT 2026 SINDECOMPRESTS"])


@router.get(
    "/cargos",
    summary="Cargos da CCT 2026",
    description="Lista todos os cargos cadastrados na CCT 2026 SINDECOMPRESTS com piso salarial e adicionais.",
)
async def listar_cargos_cct(current_user: CurrentActiveUser, db: AsyncSession = Depends(get_async_session)):
    """Lista todos os cargos da CCT 2026 SINDECOMPRESTS."""
    result = await db.execute(
        text("""
        SELECT id, cargo_nome, piso_salarial,
               adicional_insalubridade_percentual, adicional_periculosidade_percentual,
               adicional_noturno_percentual, jornada_semanal_horas, is_active
        FROM cct_cargos
        WHERE is_active = true
        ORDER BY piso_salarial DESC
    """)
    )
    rows = result.fetchall()

    return {
        "cargos": [
            {
                "id": r[0],
                "cargo_nome": r[1],
                "piso_salarial": float(r[2]) if r[2] else 0,
                "adicional_insalubridade_percentual": float(r[3]) if r[3] else 0,
                "adicional_periculosidade_percentual": float(r[4]) if r[4] else 0,
                "adicional_noturno_percentual": float(r[5]) if r[5] else 0,
                "jornada_semanal_horas": r[6],
            }
            for r in rows
        ],
        "total": len(rows),
        "sindicato": "SINDECOMPRESTS",
        "vigencia": "2026",
    }


@router.get(
    "/funcionarios",
    summary="Funcionários Vinculados à CCT",
    description="Lista funcionários com vínculo à CCT e status de conformidade salarial.",
)
async def listar_funcionarios_cct(current_user: CurrentActiveUser, db: AsyncSession = Depends(get_async_session)):
    """Lista funcionários com vínculo CCT."""
    result = await db.execute(
        text("""
        SELECT
            e.id, e.nome, e.cargo, e.salario_base,
            c.cargo_nome as cargo_cct, c.piso_salarial as piso_cct,
            c.adicional_periculosidade_percentual,
            CASE WHEN e.salario_base >= c.piso_salarial THEN 'conforme' ELSE 'abaixo_piso' END as status
        FROM employees e
        JOIN cct_cargos c ON e.cct_cargo_id::text = c.id::text
        WHERE e.is_active = true
        ORDER BY e.cargo, e.nome
    """)
    )
    rows = result.fetchall()

    return {
        "funcionarios": [
            {
                "id": r[0],
                "nome": r[1],
                "cargo": r[2],
                "salario_atual": float(r[3]) if r[3] else 0,
                "cargo_cct": r[4],
                "piso_cct": float(r[5]) if r[5] else 0,
                "adicional_periculosidade_percentual": float(r[6]) if r[6] else 0,
                "status_cct": r[7],
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.get(
    "/conformidade",
    summary="Verificar Conformidade Salarial",
    description="Identifica funcionários com salário abaixo do piso CCT e calcula custo de adequação.",
)
async def verificar_conformidade(current_user: CurrentActiveUser, db: AsyncSession = Depends(get_async_session)):
    """Verifica conformidade salarial com o piso CCT."""
    result = await db.execute(
        text("""
        SELECT
            e.nome, e.cargo, e.salario_base,
            c.cargo_nome, c.piso_salarial as piso,
            c.piso_salarial - e.salario_base as diferenca
        FROM employees e
        JOIN cct_cargos c ON e.cct_cargo_id::text = c.id::text
        WHERE e.is_active = true AND e.salario_base < c.piso_salarial
        ORDER BY (c.piso_salarial - e.salario_base) DESC
    """)
    )
    abaixo = result.fetchall()

    total_risco = sum(float(r[5]) for r in abaixo)

    return {
        "funcionarios_abaixo_piso": [
            {
                "nome": r[0],
                "cargo": r[1],
                "salario_atual": float(r[2]),
                "cargo_cct": r[3],
                "piso_cct": float(r[4]),
                "diferenca": float(r[5]),
            }
            for r in abaixo
        ],
        "total_abaixo": len(abaixo),
        "custo_adequacao_mensal": total_risco,
        "status": "regular" if not abaixo else "requer_adequacao",
        "gerado_em": datetime.now().isoformat(),
    }


@router.get(
    "/resumo",
    summary="Resumo CCT 2026",
    description="Retorna resumo geral da conformidade CCT 2026: total vinculados, abaixo do piso e custo de adequação.",
)
async def resumo_cct(current_user: CurrentActiveUser, db: AsyncSession = Depends(get_async_session)):
    """Resumo geral da conformidade CCT 2026."""
    result = await db.execute(
        text("""
        SELECT
            COUNT(*) as total,
            COUNT(cct_cargo_id) as vinculados,
            SUM(CASE WHEN e.salario_base < c.piso_salarial THEN 1 ELSE 0 END) as abaixo_piso,
            SUM(CASE WHEN e.salario_base < c.piso_salarial THEN c.piso_salarial - e.salario_base ELSE 0 END) as custo_adequacao
        FROM employees e
        LEFT JOIN cct_cargos c ON e.cct_cargo_id::text = c.id::text
        WHERE e.is_active = true
    """)
    )
    row = result.fetchone()

    total = row[0] or 0
    vinculados = row[1] or 0
    abaixo = int(row[2] or 0)
    custo = float(row[3] or 0)

    return {
        "total_funcionarios": total,
        "vinculados_cct": vinculados,
        "sem_vinculo": total - vinculados,
        "abaixo_piso_cct": abaixo,
        "custo_adequacao_mensal": custo,
        "conformidade_pct": round((vinculados / total * 100) if total else 0, 1),
        "status": "regular" if abaixo == 0 else "requer_adequacao",
        "sindicato": "SINDECOMPRESTS",
        "vigencia": "2026",
        "gerado_em": datetime.now().isoformat(),
    }


# ── Gate module:dp (padrão modules/financeiro/__init__.py) ──────────────────
# Router CCT montado DIRETO no main em /people-management/hr (fora do aggregator).
from core.permissions import requer_modulo as _requer_modulo  # noqa: E402

_dep_dp = _requer_modulo("dp")
for _route in router.routes:
    _route.dependencies.append(_dep_dp)
