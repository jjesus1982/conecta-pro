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
    MovimentacaoProgramada,
    OcorrenciaItem,
    OcorrenciaPorPosto,
    OcorrenciasPainel,
    PainelTriagem,
    PassagemHoje,
    PostoSemVigencia,
    Presenca30d,
    PresencaGeral,
    PresencaPorPosto,
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


async def _movimentacoes(db: AsyncSession) -> list[MovimentacaoProgramada]:
    """
    Movimentações programadas dos próximos 45 dias — 100% do banco:
    fins de alocação (allocations), férias (hr_vacation_requests, fonte
    canônica do DP) e vagas em aberto (posts). Tabelas vazias → lista vazia.
    """
    eventos: list[MovimentacaoProgramada] = []

    # Hoje/limite pelo relógio do banco (mesma referência das outras queries)
    hoje = (await db.execute(text("SELECT CURRENT_DATE"))).scalar()
    limite = (await db.execute(text("SELECT CURRENT_DATE + 45"))).scalar()

    # 1) Fins de alocação programados (allocations ativas com end_date futura)
    fins_result = await db.execute(
        text(
            """
            SELECT a.end_date AS data,
                   COALESCE(e.nome, a.employee_id::text) AS nome,
                   p.name AS post_nome,
                   a.notes
            FROM allocations a
            LEFT JOIN employees e ON e.id = a.employee_id
            JOIN posts p ON p.id = a.post_id
            WHERE a.status = 'active'
              AND a.is_active = true
              AND a.end_date IS NOT NULL
              AND a.end_date >= CURRENT_DATE
              AND a.end_date <= CURRENT_DATE + 45
            """
        )
    )
    for row in fins_result.fetchall():
        descricao = f"Fim: {row.nome} — {row.post_nome}"
        notes = (row.notes or "").strip()
        if notes and ("dispensa" in notes.lower() or "cobertura" in notes.lower()):
            linhas_notes = [ln.strip() for ln in notes.splitlines() if ln.strip()]
            if linhas_notes:
                descricao = f"{descricao} — {linhas_notes[-1]}"
        eventos.append(
            MovimentacaoProgramada(data=row.data, tipo="fim_alocacao", descricao=descricao[:120])
        )

    # 2) Férias (início e retorno) — fonte canônica hr_vacation_requests
    ferias_result = await db.execute(
        text(
            """
            SELECT v.start_date, v.end_date, v.return_date, v.internal_notes,
                   COALESCE(e.nome, v.employee_id::text) AS nome
            FROM hr_vacation_requests v
            LEFT JOIN employees e ON e.id = v.employee_id
            WHERE upper(v.status) IN ('APPROVED', 'IN_PROGRESS', 'SCHEDULED')
              AND (v.start_date >= CURRENT_DATE OR v.return_date >= CURRENT_DATE)
            """
        )
    )
    for row in ferias_result.fetchall():
        if row.start_date is not None and hoje <= row.start_date <= limite:
            eventos.append(
                MovimentacaoProgramada(
                    data=row.start_date,
                    tipo="inicio_ferias",
                    descricao=f"Férias: {row.nome} até {row.end_date.strftime('%d/%m/%Y')}",
                )
            )
        if row.return_date is not None and hoje <= row.return_date <= limite:
            descricao = f"Retorno de férias: {row.nome}"
            notas = (row.internal_notes or "").upper()
            if "AVISO PRÉVIO" in notas or "AVISO PREVIO" in notas:
                descricao += " — entra de AVISO PRÉVIO"
            eventos.append(
                MovimentacaoProgramada(data=row.return_date, tipo="retorno_ferias", descricao=descricao)
            )

    # 3) Vagas em aberto (posts ativos com headcount abaixo do requerido)
    vagas_result = await db.execute(
        text(
            """
            SELECT p.name AS post_nome,
                   (p.required_headcount - p.current_headcount) AS faltam
            FROM posts p
            WHERE p.is_active = true
              AND p.required_headcount > p.current_headcount
            ORDER BY p.name
            """
        )
    )
    for row in vagas_result.fetchall():
        eventos.append(
            MovimentacaoProgramada(
                data=hoje,
                tipo="vaga",
                descricao=f"Vaga aberta: {row.post_nome} ({int(row.faltam)})",
            )
        )

    eventos.sort(key=lambda ev: (ev.data, ev.tipo, ev.descricao))
    return eventos


async def _presenca_30d(db: AsyncSession) -> Presenca30d:
    """
    Absenteísmo dos últimos 30 dias (hoje-30 até ontem), por posto e geral.

    - esperados = shifts com status='scheduled' no período (cancelados/férias
      NÃO contam; folgas e turnos sem funcionário também não).
    - presentes = turno com batida real do funcionário no dia (gp_clock_punches,
      convertida p/ hora de Manaus) OU check-in manual (actual_start_time).
    - taxa = presentes/esperados (1 casa); 0 esperados → None (honesto).
    NOTA: escalas reais só existem desde 08/07 — poucos esperados no início
    da janela é o dado honesto, não inventar.
    """
    result = await db.execute(
        text(
            """
            SELECT COALESCE(p.name, 'posto não identificado') AS post_nome,
                   COUNT(*) AS dias_esperados,
                   SUM(
                       CASE
                           WHEN sh.actual_start_time IS NOT NULL
                             OR EXISTS (
                                 SELECT 1
                                 FROM gp_clock_punches cp
                                 WHERE cp.employee_id = sh.employee_id
                                   AND (cp.punch_timestamp AT TIME ZONE 'UTC'
                                        AT TIME ZONE 'America/Manaus')::date = sh.shift_date
                                   AND COALESCE(cp.status, '') NOT IN ('rejected', 'cancelado')
                             )
                           THEN 1 ELSE 0
                       END
                   ) AS dias_presentes
            FROM shifts sh
            LEFT JOIN posts p ON p.id = sh.post_id
            WHERE sh.shift_date >= CURRENT_DATE - 30
              AND sh.shift_date <= CURRENT_DATE - 1
              AND sh.status = 'scheduled'
              AND sh.is_active = true
              AND sh.is_off_day = false
              AND sh.employee_id IS NOT NULL
            GROUP BY COALESCE(p.name, 'posto não identificado')
            ORDER BY 1
            """
        )
    )

    por_posto: list[PresencaPorPosto] = []
    total_esperados = 0
    total_presentes = 0
    for row in result.fetchall():
        esperados = int(row.dias_esperados or 0)
        presentes = int(row.dias_presentes or 0)
        por_posto.append(
            PresencaPorPosto(
                post_nome=row.post_nome,
                dias_esperados=esperados,
                dias_presentes=presentes,
                taxa=round(presentes * 100.0 / esperados, 1) if esperados else None,
            )
        )
        total_esperados += esperados
        total_presentes += presentes

    geral = PresencaGeral(
        esperados=total_esperados,
        presentes=total_presentes,
        taxa=round(total_presentes * 100.0 / total_esperados, 1) if total_esperados else None,
    )
    return Presenca30d(por_posto=por_posto, geral=geral)


@router.get("/painel", response_model=PainelTriagem)
async def painel_triagem(
    scope: OperationalScope = Depends(get_operational_scope),
    db: AsyncSession = Depends(get_db),
) -> PainelTriagem:
    """
    Painel consolidado de triagem operacional — SÓ gestores.

    Agrega: ocorrências abertas, passagens de turno de hoje,
    avaliações da última semana, situação das escalas, movimentações
    programadas (45 dias) e absenteísmo dos últimos 30 dias.
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
    movimentacoes = await _movimentacoes(db)
    presenca_30d = await _presenca_30d(db)

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
        movimentacoes=movimentacoes,
        presenca_30d=presenca_30d,
    )
