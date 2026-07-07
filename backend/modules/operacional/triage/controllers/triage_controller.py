"""
Controller (endpoints) do Painel de Triagem operacional.

Rota (montada sob /api/v1/operacional):
- GET /triagem/painel → visão consolidada para GESTORES (403 para os demais)

Definições HONESTAS usadas aqui (não alterar consultor_coo_service — a
definição dele é outra):
- Ocorrência aberta  = occurrences.status IN ('aberta','em_analise') AND is_active
- Escala vigente     = scales.is_active AND status IN ('published','in_progress')
                       AND CURRENT_DATE BETWEEN start_date AND end_date
- Posto sem vigência = posts.is_active sem nenhuma escala vigente
Tabelas vazias → zeros/listas vazias (nunca fabricar dado).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.logging import logger
from modules.operacional.scope import OperationalScope, get_operational_scope
from modules.operacional.triage.schemas import (
    AvaliacaoPorPosto,
    AvaliacoesSemana,
    EscalaDraft,
    EscalasPainel,
    OcorrenciaItem,
    OcorrenciaPorPosto,
    OcorrenciasPainel,
    PainelTriagem,
    PassagemHoje,
    PostoSemVigencia,
)

router = APIRouter(prefix="/triagem", tags=["Operacional - Triagem"])

_OPEN_OCCURRENCE = "o.status IN ('aberta', 'em_analise') AND o.is_active = true"


async def _ocorrencias(db: AsyncSession) -> OcorrenciasPainel:
    total_result = await db.execute(
        text(f"SELECT COUNT(*) AS total FROM occurrences o WHERE {_OPEN_OCCURRENCE}")
    )
    abertas_total = int(total_result.scalar() or 0)

    sev_result = await db.execute(
        text(
            f"""
            SELECT o.severity, COUNT(*) AS total
            FROM occurrences o
            WHERE {_OPEN_OCCURRENCE}
            GROUP BY o.severity
            """
        )
    )
    por_severidade = {row.severity: int(row.total) for row in sev_result.fetchall()}

    posto_result = await db.execute(
        text(
            f"""
            SELECT o.post_id::text AS post_id, p.name AS post_nome, COUNT(*) AS abertas
            FROM occurrences o
            JOIN posts p ON p.id = o.post_id
            WHERE {_OPEN_OCCURRENCE}
            GROUP BY o.post_id, p.name
            ORDER BY COUNT(*) DESC
            """
        )
    )
    por_posto = [
        OcorrenciaPorPosto(post_id=row.post_id, post_nome=row.post_nome, abertas=int(row.abertas))
        for row in posto_result.fetchall()
    ]

    lista_result = await db.execute(
        text(
            f"""
            SELECT o.id::text AS id, o.code, o.title, o.severity,
                   p.name AS post_nome, o.occurred_at, o.status
            FROM occurrences o
            LEFT JOIN posts p ON p.id = o.post_id
            WHERE {_OPEN_OCCURRENCE}
            ORDER BY o.occurred_at DESC
            LIMIT 20
            """
        )
    )
    lista = [OcorrenciaItem(**dict(row._mapping)) for row in lista_result.fetchall()]

    return OcorrenciasPainel(
        abertas_total=abertas_total,
        por_severidade=por_severidade,
        por_posto=por_posto,
        lista=lista,
    )


async def _passagens_hoje(db: AsyncSession) -> list[PassagemHoje]:
    result = await db.execute(
        text(
            """
            SELECT p.name AS post_nome, pt.turno, pt.author_nome,
                   pt.resumo, pt.pendencias, pt.criada_em
            FROM operacional_passagens_turno pt
            JOIN posts p ON p.id = pt.post_id
            WHERE pt.data_turno = CURRENT_DATE AND pt.is_active = true
            ORDER BY pt.criada_em DESC
            """
        )
    )
    return [PassagemHoje(**dict(row._mapping)) for row in result.fetchall()]


async def _avaliacoes_semana(db: AsyncSession) -> AvaliacoesSemana:
    geral_result = await db.execute(
        text(
            """
            SELECT COUNT(*) AS total, AVG(av.nota) AS media
            FROM operacional_avaliacoes_equipe av
            WHERE av.is_active = true
              AND av.criada_em >= NOW() - INTERVAL '7 days'
            """
        )
    )
    geral = geral_result.first()
    total = int(geral.total or 0)
    media_geral = round(float(geral.media), 2) if geral.media is not None else None

    posto_result = await db.execute(
        text(
            """
            SELECT p.name AS post_nome, AVG(av.nota) AS media, COUNT(*) AS total
            FROM operacional_avaliacoes_equipe av
            JOIN posts p ON p.id = av.post_id
            WHERE av.is_active = true
              AND av.criada_em >= NOW() - INTERVAL '7 days'
            GROUP BY p.name
            ORDER BY AVG(av.nota) ASC
            """
        )
    )
    por_posto = [
        AvaliacaoPorPosto(post_nome=row.post_nome, media=round(float(row.media), 2), total=int(row.total))
        for row in posto_result.fetchall()
    ]

    return AvaliacoesSemana(total=total, media_geral=media_geral, por_posto=por_posto)


async def _escalas(db: AsyncSession) -> EscalasPainel:
    sem_vigencia_result = await db.execute(
        text(
            """
            SELECT p.id::text AS post_id, p.name AS post_nome
            FROM posts p
            WHERE p.is_active = true
              AND NOT EXISTS (
                  SELECT 1
                  FROM scales s
                  WHERE s.post_id = p.id
                    AND s.is_active = true
                    AND s.status IN ('published', 'in_progress')
                    AND s.start_date IS NOT NULL
                    AND s.end_date IS NOT NULL
                    AND CURRENT_DATE BETWEEN s.start_date AND s.end_date
              )
            ORDER BY p.name
            """
        )
    )
    sem_vigencia = [PostoSemVigencia(**dict(row._mapping)) for row in sem_vigencia_result.fetchall()]

    drafts_result = await db.execute(
        text(
            """
            SELECT s.id::text AS id, s.name, s.month, s.year,
                   p.name AS post_nome, s.status
            FROM scales s
            JOIN posts p ON p.id = s.post_id
            WHERE s.is_active = true AND s.status = 'draft'
            ORDER BY s.year DESC, s.month DESC
            """
        )
    )
    drafts = [EscalaDraft(**dict(row._mapping)) for row in drafts_result.fetchall()]

    return EscalasPainel(sem_vigencia=sem_vigencia, drafts=drafts)


@router.get("/painel", response_model=PainelTriagem)
async def painel_triagem(
    scope: OperationalScope = Depends(get_operational_scope),
    db: AsyncSession = Depends(get_db),
) -> PainelTriagem:
    """
    Painel consolidado de triagem operacional — SÓ gestores.

    Agrega: ocorrências abertas, passagens de turno de hoje,
    avaliações da última semana e situação das escalas.
    """
    if not scope.is_manager:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Painel de triagem é restrito a gestores.",
        )

    ocorrencias = await _ocorrencias(db)
    passagens_hoje = await _passagens_hoje(db)
    avaliacoes_semana = await _avaliacoes_semana(db)
    escalas = await _escalas(db)

    logger.info(
        "Painel de triagem consultado",
        action="painel_triagem",
        user_id=scope.user_id,
        ocorrencias_abertas=ocorrencias.abertas_total,
        passagens_hoje=len(passagens_hoje),
    )

    return PainelTriagem(
        ocorrencias=ocorrencias,
        passagens_hoje=passagens_hoje,
        avaliacoes_semana=avaliacoes_semana,
        escalas=escalas,
    )
