"""
Controller de Clima Organizacional para RH.

Fornece dashboard com indicadores de clima e absenteismo,
preparado para receber dados de pesquisas futuras.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/climate", tags=["RH - Clima"])


@router.get("/dashboard")
async def climate_dashboard(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Dashboard de clima organizacional."""
    try:
        total = (await db.execute(text("SELECT count(*) FROM employees WHERE status = 'ativo'"))).scalar() or 0

        por_escala = (
            (
                await db.execute(
                    text(
                        "SELECT escala_padrao, count(*) as qtd FROM employees "
                        "WHERE status = 'ativo' GROUP BY escala_padrao ORDER BY qtd DESC"
                    )
                )
            )
            .mappings()
            .all()
        )

        # [RH] eram literais 0 — ler o real (climate_surveys / sst_afastamentos ativos)
        pesquisas = (await db.execute(text("SELECT COUNT(*) FROM climate_surveys"))).scalar() or 0
        alertas_abs = (
            await db.execute(text("SELECT COUNT(*) FROM sst_afastamentos WHERE data_retorno IS NULL"))
        ).scalar() or 0
        return {
            "total_colaboradores": total,
            "pesquisas_realizadas": pesquisas,
            "nps_colaborador": None,
            "indice_satisfacao": None,
            "alertas_absenteismo": alertas_abs,
            "distribuicao_escala": [dict(r) for r in por_escala],
            "status": "ativo" if pesquisas else "aguardando_pesquisa",
            "message": "Indicadores de clima." if pesquisas else "Realize a primeira pesquisa de clima para gerar indicadores.",
        }
    except Exception as exc:
        logger.warning("Erro no dashboard clima: %s", exc)
        return {"total_colaboradores": 0, "status": "erro"}


@router.get("/surveys")
async def climate_surveys(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    page: int = 1,
    page_size: int = 20,
) -> Any:
    """Lista pesquisas de clima organizacional."""
    try:
        offset = (page - 1) * page_size
        rows = (
            (
                await db.execute(
                    text(
                        "SELECT id::text, nome, descricao, frequencia, ativo, "
                        "data_inicio, data_fim, total_respostas, score_medio, created_at "
                        "FROM climate_surveys ORDER BY created_at DESC "
                        "LIMIT :limit OFFSET :offset"
                    ),
                    {"limit": page_size, "offset": offset},
                )
            )
            .mappings()
            .all()
        )
        total = (await db.execute(text("SELECT COUNT(*) FROM climate_surveys"))).scalar() or 0
        items = [dict(r) for r in rows]
        return {"items": items, "total": total, "page": page, "page_size": page_size}
    except Exception as exc:
        logger.warning("Erro ao listar pesquisas de clima: %s", exc)
        return {"items": [], "total": 0, "message": "Nenhuma pesquisa cadastrada ainda."}


@router.get("/alerts")
async def climate_alerts(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Lista alertas de clima organizacional."""
    return {"items": [], "total": 0}


@router.get("/absenteismo/alertas")
async def absenteismo_alertas(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Alertas de absenteismo ativos."""
    try:
        alertas = (await db.execute(text("SELECT * FROM rh_alertas_absenteismo"))).mappings().all()
        return {"alertas": [dict(r) for r in alertas], "total": len(alertas)}
    except Exception as exc:
        logger.warning("Erro ao buscar alertas: %s", exc)
        return {"alertas": [], "total": 0}


@router.get("/absenteismo/dashboard")
async def absenteismo_dashboard(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Dashboard de absenteismo."""
    try:
        stats = (
            (
                await db.execute(
                    text(
                        "SELECT count(*) as afastamentos_ativos, "
                        "COALESCE(SUM(CURRENT_DATE - data_inicio), 0) as total_dias_perdidos, "
                        "ROUND(count(*) * 100.0 / NULLIF((SELECT count(*) FROM employees), 0), 2) "
                        "as taxa_absenteismo, "
                        "COALESCE(SUM(CASE WHEN ajuda_medicamento_ativa THEN "
                        "ajuda_medicamento_valor ELSE 0 END), 0) as custo_ajuda "
                        "FROM sst_afastamentos "
                        "WHERE data_fim_prevista IS NULL OR data_fim_prevista >= CURRENT_DATE"
                    )
                )
            )
            .mappings()
            .first()
        )
        return (
            dict(stats)
            if stats
            else {
                "afastamentos_ativos": 0,
                "total_dias_perdidos": 0,
                "taxa_absenteismo": 0,
                "custo_ajuda": 0,
            }
        )
    except Exception as exc:
        logger.warning("Erro no dashboard absenteismo: %s", exc)
        return {"afastamentos_ativos": 0}
