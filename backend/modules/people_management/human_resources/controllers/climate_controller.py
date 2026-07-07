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


PARTICIPACAO_MINIMA_PCT = 30.0
SCORE_MINIMO_ALERTA = 6.0


@router.get("/dashboard")
async def climate_dashboard(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Dashboard de clima organizacional — scores reais por pesquisa e geral.

    Sem respostas registradas, retorna estrutura honesta em
    "aguardando_respostas": respostas de clima sao opiniao de gente real
    e NUNCA sao fabricadas.
    """
    try:
        ativos = (await db.execute(text("SELECT count(*) FROM employees WHERE status = 'ativo'"))).scalar() or 0

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

        # Scores reais por pesquisa (a partir das respostas existentes)
        por_pesquisa = (
            (
                await db.execute(
                    text(
                        "SELECT s.id::text, s.nome, s.ativo, s.data_inicio, s.data_fim, "
                        "COUNT(r.id) AS respostas, "
                        "COUNT(DISTINCT r.funcionario_hash) AS respondentes, "
                        "ROUND(AVG(r.score_calculado)::numeric, 2) AS score_medio "
                        "FROM climate_surveys s "
                        "LEFT JOIN climate_responses r ON r.survey_id = s.id "
                        "GROUP BY s.id, s.nome, s.ativo, s.data_inicio, s.data_fim "
                        "ORDER BY s.created_at DESC"
                    )
                )
            )
            .mappings()
            .all()
        )

        pesquisas_out = []
        for p in por_pesquisa:
            d = dict(p)
            respondentes = d.get("respondentes") or 0
            d["score_medio"] = float(d["score_medio"]) if d["score_medio"] is not None else None
            d["participacao_pct"] = round(respondentes * 100.0 / ativos, 1) if ativos else None
            pesquisas_out.append(d)

        respostas_total = (await db.execute(text("SELECT count(*) FROM climate_responses"))).scalar() or 0
        respondentes_unicos = (
            await db.execute(text("SELECT count(DISTINCT funcionario_hash) FROM climate_responses"))
        ).scalar() or 0

        score_geral = None
        if respostas_total:
            score_geral = (
                await db.execute(text("SELECT ROUND(AVG(score_calculado)::numeric, 2) FROM climate_responses"))
            ).scalar()
            score_geral = float(score_geral) if score_geral is not None else None

        alertas_abs = (
            await db.execute(text("SELECT COUNT(*) FROM sst_afastamentos WHERE data_retorno IS NULL"))
        ).scalar() or 0

        tem_pesquisa = len(pesquisas_out) > 0
        if not tem_pesquisa:
            status, message = "aguardando_pesquisa", "Realize a primeira pesquisa de clima para gerar indicadores."
        elif respostas_total == 0:
            status = "aguardando_respostas"
            message = (
                f"{len(pesquisas_out)} pesquisa(s) cadastrada(s), 0 respostas registradas. "
                "Scores aparecerao quando os colaboradores responderem — respostas nunca sao fabricadas."
            )
        else:
            status, message = "ativo", "Indicadores calculados sobre respostas reais."

        return {
            "total_colaboradores": ativos,
            "pesquisas_realizadas": len(pesquisas_out),
            "respostas_total": respostas_total,
            "score_geral": score_geral,
            "participacao": {
                "respondentes_unicos": respondentes_unicos,
                "funcionarios_ativos": ativos,
                "percentual": round(respondentes_unicos * 100.0 / ativos, 1) if ativos else None,
            },
            "por_pesquisa": pesquisas_out,
            "nps_colaborador": None if respostas_total == 0 else score_geral,
            "indice_satisfacao": score_geral,
            "alertas_absenteismo": alertas_abs,
            "distribuicao_escala": [dict(r) for r in por_escala],
            "status": status,
            "message": message,
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
    """Alertas de clima calculados sobre dados reais e persistidos.

    Regras (so avaliadas em pesquisas ativas COM respostas reais):
    - score medio da pesquisa < 6.0  -> alerta score_baixo
    - participacao < 30% dos ativos  -> alerta participacao_baixa
    Sem respostas nao ha alerta — apenas nota honesta.
    """
    try:
        ativos = (await db.execute(text("SELECT count(*) FROM employees WHERE status = 'ativo'"))).scalar() or 0
        stats = (
            (
                await db.execute(
                    text(
                        "SELECT s.id, s.nome, COUNT(r.id) AS respostas, "
                        "COUNT(DISTINCT r.funcionario_hash) AS respondentes, "
                        "AVG(r.score_calculado) AS score_medio "
                        "FROM climate_surveys s "
                        "LEFT JOIN climate_responses r ON r.survey_id = s.id "
                        "WHERE s.ativo IS TRUE "
                        "GROUP BY s.id, s.nome"
                    )
                )
            )
            .mappings()
            .all()
        )

        gerados = 0
        for s in stats:
            if not s["respostas"]:
                continue  # sem resposta real -> sem alerta (nunca fabricar)

            score = round(float(s["score_medio"]), 2) if s["score_medio"] is not None else None
            participacao = round(s["respondentes"] * 100.0 / ativos, 1) if ativos else None

            candidatos = []
            if score is not None and score < SCORE_MINIMO_ALERTA:
                candidatos.append(
                    (
                        "score_baixo",
                        "alta" if score < 4 else "media",
                        f"Pesquisa '{s['nome']}' com score medio {score} "
                        f"(abaixo do limiar {SCORE_MINIMO_ALERTA}).",
                        score,
                    )
                )
            if participacao is not None and participacao < PARTICIPACAO_MINIMA_PCT:
                candidatos.append(
                    (
                        "participacao_baixa",
                        "media",
                        f"Pesquisa '{s['nome']}' com participacao de {participacao}% "
                        f"({s['respondentes']}/{ativos} ativos) — abaixo de {PARTICIPACAO_MINIMA_PCT:.0f}%.",
                        score,
                    )
                )

            for tipo, severidade, mensagem, score_atual in candidatos:
                ja_existe = (
                    await db.execute(
                        text(
                            "SELECT 1 FROM climate_alerts WHERE entidade_id = :sid "
                            "AND tipo_alerta = :tipo AND resolvido IS NOT TRUE LIMIT 1"
                        ),
                        {"sid": s["id"], "tipo": tipo},
                    )
                ).scalar()
                if ja_existe:
                    continue
                await db.execute(
                    text(
                        "INSERT INTO climate_alerts "
                        "(id, entidade_tipo, entidade_id, entidade_nome, periodo, tipo_alerta, "
                        "severidade, mensagem, score_atual, resolvido, created_at) "
                        "VALUES (gen_random_uuid(), 'survey', :sid, :nome, to_char(now(), 'YYYY-MM'), "
                        ":tipo, :severidade, :mensagem, :score, false, now())"
                    ),
                    {
                        "sid": s["id"],
                        "nome": s["nome"],
                        "tipo": tipo,
                        "severidade": severidade,
                        "mensagem": mensagem,
                        "score": score_atual,
                    },
                )
                gerados += 1
        if gerados:
            await db.commit()

        rows = (
            (
                await db.execute(
                    text(
                        "SELECT id::text, entidade_tipo, entidade_id::text, entidade_nome, periodo, "
                        "tipo_alerta, severidade, mensagem, score_atual, resolvido, created_at "
                        "FROM climate_alerts WHERE resolvido IS NOT TRUE "
                        "ORDER BY created_at DESC LIMIT 100"
                    )
                )
            )
            .mappings()
            .all()
        )
        items = [dict(r) for r in rows]

        total_respostas = sum(s["respostas"] or 0 for s in stats)
        nota = None
        if not items and total_respostas == 0:
            nota = (
                "Nenhum alerta: as pesquisas ativas ainda nao tem respostas reais. "
                "Alertas so sao gerados sobre respostas de colaboradores — nunca fabricados."
            )
        return {"items": items, "total": len(items), "gerados_nesta_consulta": gerados, "nota": nota}
    except Exception as exc:
        logger.warning("Erro ao calcular alertas de clima: %s", exc)
        return {"items": [], "total": 0, "erro": str(exc)}


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
