"""
Controller do Quadro de Presença ao vivo (Operacional).

Rotas (montadas sob /api/v1/operacional):
- GET  /presenca/hoje                       → quadro escala × batidas reais do dia
- POST /presenca/checkin-manual/{shift_id}  → check-in manual pelo líder/gestor

FONTES (100% reais — NUNCA fabricar presença):
- shifts: ESPERADOS do dia (employee_id preenchido, não folga, não cancelado).
- gp_clock_punches: batidas sincronizadas do Sólides. A 1ª batida DENTRO DA
  JANELA DO TURNO = presença com fonte='ponto'. gp_clock_punches.posto_id é
  SEMPRE NULL — o vínculo com posto sai do shift (esperados) ou da alocação (extras).
- shifts.actual_start_time: check-in manual = presença com fonte='manual'.
- allocations/posts: agrupam EXTRAS (batida sem turno) pelo posto da alocação
  ativa; allocations.setor identifica o setor do funcionário.

JANELA DE PRESENÇA POR TURNO (batida fora da janela NÃO conta):
- DIURNO (planned_start < 15:00): [planned_start − 2h, planned_end]. Evita que
  a batida de ~05h (SAÍDA do noturno de ontem) marque presença do diurno.
- NOTURNO (planned_start >= 15:00): [planned_start − 2h do dia D, D+1 07:00].
  Evita que uma batida da madrugada de HOJE marque "presente" um noturno que
  só começa às ~18h.
- EXTRAS: batida do dia sem turno correspondente hoje. Batida antes das 07:00
  de quem teve turno NOTURNO ontem (shift_date = D−1, is_night_shift) é a
  SAÍDA do turno de ontem — não é extra; contada em resumo.saidas_noturno_ontem.

DECISÃO DE TIMEZONE (America/Manaus):
- A operação é em Manaus-AM. Tanto shifts.planned_start_time/planned_end_time
  quanto gp_clock_punches.punch_timestamp é gravado em UTC (provado 2026-07-08: ASG 11:02 UTC = 07:02 Manaus); shifts são
  NAIVE em hora LOCAL de Manaus.
- Por isso "agora" = datetime.now(America/Manaus) com tzinfo removido (naive
  local), comparado direto com planned_* combinados à data consultada.
- NUNCA comparar com hora do servidor/UTC: Manaus é UTC-4 e um turno das 07:00
  apareceria "atrasado" 4 horas antes da hora real.
- O check-in manual grava actual_start_time também em hora local de Manaus,
  coerente com punch_timestamp.

Escopo: líder de posto vê/opera só os postos dele; gestor vê tudo; demais → 403
(scope_post_ids_or_403).
"""

import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.logging import logger
from modules.operacional.presence.schemas import (
    CheckinManualBody,
    ExtraPresenca,
    FuncionarioTurno,
    PostoPresenca,
    QuadroPresenca,
    ResumoPresenca,
)
from modules.operacional.scope import (
    OperationalScope,
    get_operational_scope,
    scope_post_ids_or_403,
)

router = APIRouter(prefix="/presenca", tags=["Operacional - Presença"])

TZ_MANAUS = ZoneInfo("America/Manaus")

# Janela de tolerância antes de marcar "atrasado" (regra do quadro, não da CCT)
TOLERANCIA_ATRASO = timedelta(minutes=15)

# Janelas de presença por turno (ver docstring do módulo)
HORA_CORTE_NOTURNO = time(15, 0)   # planned_start >= 15:00 → turno noturno
JANELA_PRE_TURNO = timedelta(hours=2)  # batida aceita até 2h antes do início
FIM_JANELA_NOTURNO = time(7, 0)    # noturno aceita batida até D+1 07:00; madrugada < 07:00 pode ser saída do noturno de ontem

# Batida válida = não rejeitada/cancelada; COALESCE protege status NULL
# (NOT IN com NULL excluiria a linha silenciosamente).
_PUNCH_VALIDO = "COALESCE(cp.status, '') NOT IN ('rejected', 'cancelado')"

# Turno que conta como "esperado" no dia
_SHIFT_ESPERADO = (
    "sh.employee_id IS NOT NULL "
    "AND sh.is_off_day = FALSE "
    "AND sh.status <> 'cancelled' "
    "AND sh.is_active = TRUE"
)


def _janela_turno(dia: date, inicio: time, fim: time) -> tuple[datetime, datetime]:
    """Combina data + horários planejados. Turno noturno (fim <= início) termina no dia seguinte."""
    dt_inicio = datetime.combine(dia, inicio)
    dt_fim = datetime.combine(dia, fim)
    if dt_fim <= dt_inicio:
        dt_fim += timedelta(days=1)
    return dt_inicio, dt_fim


def _janela_presenca(dia: date, inicio: time, fim: time) -> tuple[datetime, datetime]:
    """
    Janela de batidas que CONTAM como presença do turno (hora local de Manaus):
    - DIURNO (início < 15:00): [início − 2h, fim planejado].
    - NOTURNO (início >= 15:00): [início − 2h do dia D, D+1 07:00].
    Batida fora da janela não marca presença deste turno.
    """
    dt_inicio, dt_fim = _janela_turno(dia, inicio, fim)
    if inicio >= HORA_CORTE_NOTURNO:
        dt_fim = datetime.combine(dia + timedelta(days=1), FIM_JANELA_NOTURNO)
    return dt_inicio - JANELA_PRE_TURNO, dt_fim


def _primeira_batida_na_janela(
    batidas_emp: list[dict], ini: datetime, fim: datetime
) -> dict | None:
    """1ª batida do funcionário dentro da janela [ini, fim] (lista já vem em ordem cronológica)."""
    for b in batidas_emp:
        if ini <= b["punch_timestamp"] <= fim:
            return b
    return None


def _status_turno(agora: datetime, dt_inicio: datetime, dt_fim: datetime) -> str:
    """
    Status HONESTO de um turno SEM presença registrada (hora local de Manaus):
    - 'aguardando' → agora < início + 15min
    - 'atrasado'   → início + 15min < agora < fim
    - 'ausente'    → agora >= fim
    (Com presença o chamador já devolve 'presente' antes de chegar aqui.)
    """
    if agora < dt_inicio + TOLERANCIA_ATRASO:
        return "aguardando"
    if agora >= dt_fim:
        return "ausente"
    return "atrasado"


async def _batidas_por_funcionario(db: AsyncSession, dia: date) -> dict[str, list[dict]]:
    """
    Batidas válidas por funcionário em [dia 00:00, dia+1 07:00), hora local de
    Manaus, em ordem cronológica: {employee_id: [{punch_timestamp, facial_match,
    dentro_geofence}, ...]}. A cauda de D+1 (até 07:00) existe porque a janela
    de presença do turno NOTURNO de hoje atravessa a meia-noite.
    """
    result = await db.execute(
        text(
            f"""
            SELECT cp.employee_id::text AS employee_id,
                   (cp.punch_timestamp) AS punch_timestamp,
                   cp.facial_match,
                   cp.dentro_geofence
            FROM gp_clock_punches cp
            WHERE (cp.punch_timestamp) >= :ini
              AND (cp.punch_timestamp) < :fim
              AND {_PUNCH_VALIDO}
              AND cp.employee_id NOT IN (SELECT id FROM employees WHERE coalesce(is_homologacao, false) = true)
            ORDER BY cp.employee_id, (cp.punch_timestamp) ASC
            """
        ),
        {
            "ini": datetime.combine(dia, time.min),
            "fim": datetime.combine(dia + timedelta(days=1), FIM_JANELA_NOTURNO),
        },
    )
    batidas: dict[str, list[dict]] = {}
    for row in result.fetchall():
        batidas.setdefault(row.employee_id, []).append(dict(row._mapping))
    return batidas


@router.get("/hoje", response_model=QuadroPresenca)
async def quadro_presenca_hoje(
    data: date | None = None,
    scope: OperationalScope = Depends(get_operational_scope),
    db: AsyncSession = Depends(get_db),
) -> QuadroPresenca:
    """
    Quadro de presença do dia (default: hoje em Manaus), escopado por posto.

    Por posto ativo do escopo: esperados (shifts do dia) × presença real
    (1ª batida gp_clock_punches OU check-in manual) + extras (batida sem shift,
    agrupados pela alocação ativa). Dia sem shifts → postos com esperados=0.
    """
    post_ids = scope_post_ids_or_403(scope)  # None = vê todos os postos

    # Hora local de Manaus, naive — mesma referência dos timestamps do banco (ver docstring do módulo)
    agora = datetime.now(TZ_MANAUS).replace(tzinfo=None)
    dia = data or agora.date()

    scope_filter_posts = " AND p.id IN :pids" if post_ids is not None else ""
    scope_filter_shifts = " AND sh.post_id IN :pids" if post_ids is not None else ""

    def _bind(sql: str):
        stmt = text(sql)
        if post_ids is not None:
            stmt = stmt.bindparams(bindparam("pids", expanding=True))
        return stmt

    params: dict = {"dia": dia}
    if post_ids is not None:
        params["pids"] = post_ids

    # ── Postos ativos do escopo (base do quadro — aparecem mesmo com 0 esperados)
    postos_result = await db.execute(
        _bind(
            f"""
            SELECT p.id::text AS post_id, p.name AS post_nome
            FROM posts p
            WHERE p.is_active = TRUE{scope_filter_posts}
              -- Posto-base de homologação NÃO entra no quadro operacional de produção
              AND coalesce(p.code, '') <> 'CONECTA-BASE'
            ORDER BY p.name
            """
        ),
        {k: v for k, v in params.items() if k != "dia"},
    )
    postos: dict[str, dict] = {
        row.post_id: {
            "post_id": row.post_id,
            "post_nome": row.post_nome,
            "funcionarios": [],
            "extras": [],
        }
        for row in postos_result.fetchall()
    }

    # ── ESPERADOS: shifts do dia (escopados) JOIN employees
    shifts_result = await db.execute(
        _bind(
            f"""
            SELECT sh.id::text AS shift_id,
                   sh.post_id::text AS post_id,
                   p.name AS post_nome,
                   sh.employee_id::text AS employee_id,
                   e.nome, e.cargo,
                   sh.planned_start_time, sh.planned_end_time,
                   sh.actual_start_time,
                   sh.status AS shift_status,
                   aloc.setor,
                   sub.status AS substituicao
            FROM shifts sh
            JOIN employees e ON e.id = sh.employee_id
            JOIN posts p ON p.id = sh.post_id
            LEFT JOIN LATERAL (
                SELECT a.setor
                FROM allocations a
                WHERE a.employee_id = sh.employee_id
                  AND a.status = 'active' AND a.is_active = TRUE
                ORDER BY (a.post_id = sh.post_id) DESC, a.is_primary DESC, a.created_at DESC
                LIMIT 1
            ) aloc ON TRUE
            LEFT JOIN LATERAL (
                SELECT su.status
                FROM substitutions su
                WHERE su.shift_id = sh.id AND su.is_active
                  AND su.status IN ('pending', 'confirmed')
                ORDER BY su.requested_at DESC
                LIMIT 1
            ) sub ON TRUE
            WHERE sh.shift_date = :dia
              AND {_SHIFT_ESPERADO}{scope_filter_shifts}
              AND coalesce(e.is_homologacao, false) = false
            ORDER BY p.name, sh.planned_start_time, e.nome
            """
        ),
        params,
    )
    shift_rows = shifts_result.fetchall()

    # ── Batidas do dia (+ cauda D+1 até 07:00 p/ noturno) — sem filtro de posto:
    #    gp_clock_punches.posto_id é sempre NULL; escopo entra pelo shift/alocação
    batidas = await _batidas_por_funcionario(db, dia)

    for row in shift_rows:
        # Posto do shift pode estar fora da base (ex.: posto inativado com escala publicada)
        posto = postos.setdefault(
            row.post_id,
            {"post_id": row.post_id, "post_nome": row.post_nome, "funcionarios": [], "extras": []},
        )

        # FIX A: só batida DENTRO da janela do turno conta como presença dele
        janela_ini, janela_fim = _janela_presenca(dia, row.planned_start_time, row.planned_end_time)
        batida = _primeira_batida_na_janela(batidas.get(row.employee_id, []), janela_ini, janela_fim)
        if batida is not None:
            # (a) fonte primária: 1ª batida real dentro da janela do turno
            presenca_em, fonte = batida["punch_timestamp"], "ponto"
            facial, geofence = batida["facial_match"], batida["dentro_geofence"]
            status_turno = "presente"
        elif row.actual_start_time is not None:
            # (b) fallback: check-in manual (shifts.actual_start_time)
            presenca_em, fonte = row.actual_start_time, "manual"
            facial = geofence = None
            status_turno = "presente"
        else:
            # Sem NENHUMA presença registrada → status honesto pelo horário planejado
            presenca_em = fonte = facial = geofence = None
            dt_inicio, dt_fim = _janela_turno(dia, row.planned_start_time, row.planned_end_time)
            status_turno = _status_turno(agora, dt_inicio, dt_fim)

        # Falta registrada pelo líder/gestor (shift 'missed') e sem presença que a
        # contradiga → o quadro mostra 'ausente' já, sem esperar a janela vencer
        falta_registrada = row.shift_status == "missed"
        if falta_registrada and status_turno != "presente":
            status_turno = "ausente"

        posto["funcionarios"].append(
            FuncionarioTurno(
                employee_id=row.employee_id,
                nome=row.nome,
                cargo=row.cargo,
                setor=row.setor,
                shift_id=row.shift_id,
                turno_inicio=row.planned_start_time,
                turno_fim=row.planned_end_time,
                status=status_turno,
                presenca_em=presenca_em,
                fonte=fonte,
                facial_match=facial,
                dentro_geofence=geofence,
                falta_registrada=falta_registrada,
                substituicao=row.substituicao,
            )
        )

    # ── EXTRAS: batida hoje SEM shift hoje (comparado contra TODOS os shifts do
    #    dia, não só os do escopo — quem tem turno em outro posto não é "extra")
    esperados_global_result = await db.execute(
        text(
            f"""
            SELECT DISTINCT sh.employee_id::text
            FROM shifts sh
            WHERE sh.shift_date = :dia AND {_SHIFT_ESPERADO}
            """
        ),
        {"dia": dia},
    )
    esperados_global = {r[0] for r in esperados_global_result.fetchall()}

    # Candidatos a extra: batidas com data local = dia (a cauda de D+1 até 07:00
    # pertence à janela do noturno de HOJE, nunca vira extra do dia)
    candidatos_extras: dict[str, list[dict]] = {}
    for emp_id, punches in batidas.items():
        if emp_id in esperados_global:
            continue
        do_dia = [b for b in punches if b["punch_timestamp"].date() == dia]
        if do_dia:
            candidatos_extras[emp_id] = do_dia

    # Quem teve turno NOTURNO ontem: batida antes das 07:00 é a SAÍDA do turno
    # de ontem, não presença extra de hoje (só consulta se houver madrugada)
    noturno_ontem: set[str] = set()
    madrugada_ids = [
        emp_id
        for emp_id, punches in candidatos_extras.items()
        if punches[0]["punch_timestamp"].time() < FIM_JANELA_NOTURNO
    ]
    if madrugada_ids:
        noturno_ontem_result = await db.execute(
            text(
                f"""
                SELECT DISTINCT sh.employee_id::text
                FROM shifts sh
                WHERE sh.shift_date = :ontem
                  AND sh.is_night_shift = TRUE
                  AND sh.employee_id IN :emp_ids
                  AND {_SHIFT_ESPERADO}
                """
            ).bindparams(bindparam("emp_ids", expanding=True)),
            {"ontem": dia - timedelta(days=1), "emp_ids": madrugada_ids},
        )
        noturno_ontem = {r[0] for r in noturno_ontem_result.fetchall()}

    saidas_noturno_ontem = 0
    extras_batida: dict[str, dict] = {}  # employee_id → batida que conta como extra
    for emp_id, punches in candidatos_extras.items():
        primeira = punches[0]
        if primeira["punch_timestamp"].time() < FIM_JANELA_NOTURNO and emp_id in noturno_ontem:
            # Madrugada de quem fez noturno ontem = saída do turno de ontem
            saidas_noturno_ontem += 1
            # Só é extra REAL se houver OUTRA batida a partir das 07:00
            restantes = [b for b in punches if b["punch_timestamp"].time() >= FIM_JANELA_NOTURNO]
            if not restantes:
                continue
            primeira = restantes[0]
        extras_batida[emp_id] = primeira

    extras_ids = list(extras_batida)

    sem_posto: list[ExtraPresenca] = []
    if extras_ids:
        extras_result = await db.execute(
            text(
                """
                SELECT DISTINCT ON (e.id)
                       e.id::text AS employee_id, e.nome,
                       a.post_id::text AS aloc_post_id,
                       p.name AS aloc_post_nome,
                       a.setor
                FROM employees e
                LEFT JOIN allocations a
                       ON a.employee_id = e.id AND a.status = 'active' AND a.is_active = TRUE
                LEFT JOIN posts p ON p.id = a.post_id
                WHERE e.id IN :emp_ids
                ORDER BY e.id, a.is_primary DESC, a.created_at DESC
                """
            ).bindparams(bindparam("emp_ids", expanding=True)),
            {"emp_ids": extras_ids},
        )
        for row in extras_result.fetchall():
            batida = extras_batida[row.employee_id]
            extra = ExtraPresenca(
                employee_id=row.employee_id,
                nome=row.nome,
                setor=row.setor,
                presenca_em=batida["punch_timestamp"],
                fonte="ponto",
            )
            if row.aloc_post_id:
                if row.aloc_post_id in postos:
                    postos[row.aloc_post_id]["extras"].append(extra)
                elif post_ids is None:
                    # Gestor: posto da alocação fora da base (ex.: inativo) ainda aparece
                    postos.setdefault(
                        row.aloc_post_id,
                        {"post_id": row.aloc_post_id, "post_nome": row.aloc_post_nome,
                         "funcionarios": [], "extras": []},
                    )["extras"].append(extra)
                # Líder escopado: extra alocado a posto FORA do escopo não é exibido
            elif post_ids is None:
                # Sem alocação ativa → grupo "sem_posto" (só gestores; para o líder
                # escopado esse dado não pertence a nenhum posto dele)
                sem_posto.append(extra)

    # ── Montagem final + resumo (contagens derivadas do que foi apurado, nunca inventadas)
    postos_out: list[PostoPresenca] = []
    resumo = {
        "esperados": 0,
        "presentes": 0,
        "atrasados": 0,
        "ausentes": 0,
        "aguardando": 0,
        "extras": 0,
        "saidas_noturno_ontem": saidas_noturno_ontem,
    }
    for p in sorted(postos.values(), key=lambda x: (x["post_nome"] or "")):
        contagem = {"presente": 0, "atrasado": 0, "ausente": 0, "aguardando": 0}
        for f in p["funcionarios"]:
            contagem[f.status] += 1
        postos_out.append(
            PostoPresenca(
                post_id=p["post_id"],
                post_nome=p["post_nome"],
                esperados=len(p["funcionarios"]),
                presentes=contagem["presente"],
                atrasados=contagem["atrasado"],
                ausentes=contagem["ausente"],
                aguardando=contagem["aguardando"],
                funcionarios=p["funcionarios"],
                extras=p["extras"],
            )
        )
        resumo["esperados"] += len(p["funcionarios"])
        resumo["presentes"] += contagem["presente"]
        resumo["atrasados"] += contagem["atrasado"]
        resumo["ausentes"] += contagem["ausente"]
        resumo["aguardando"] += contagem["aguardando"]
        resumo["extras"] += len(p["extras"])
    resumo["extras"] += len(sem_posto)

    logger.info(
        "Quadro de presença consultado",
        action="presenca_hoje",
        user_id=scope.user_id,
        data=dia.isoformat(),
        esperados=resumo["esperados"],
        presentes=resumo["presentes"],
        extras=resumo["extras"],
    )

    ultima_sync = (
        await db.execute(
            text("SELECT max(punch_timestamp) FROM gp_clock_punches")
        )
    ).scalar()

    return QuadroPresenca(
        data=dia,
        atualizado_em=agora,
        batidas_sincronizadas_ate=ultima_sync,
        resumo=ResumoPresenca(**resumo),
        postos=postos_out,
        sem_posto=sem_posto,
    )


@router.post("/checkin-manual/{shift_id}", response_model=FuncionarioTurno)
async def checkin_manual(
    shift_id: str,
    payload: CheckinManualBody | None = None,
    scope: OperationalScope = Depends(get_operational_scope),
    db: AsyncSession = Depends(get_db),
) -> FuncionarioTurno:
    """
    Check-in manual de um turno de HOJE pelo líder do posto ou gestor.

    Existe porque o check-in nativo de shifts não aplica escopo por posto.
    Regras: shift existe (404), é de hoje (400), posto no escopo (403),
    sem presença ainda — nem batida nem manual (409). Seta actual_start_time
    (hora local de Manaus) + status='in_progress' e registra a autoria em notes.
    """
    post_ids = scope_post_ids_or_403(scope)  # None = gestor (todos os postos)

    # UUID malformado no path → 404 honesto (evita 500 do driver)
    try:
        uuid.UUID(shift_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turno não encontrado.")

    agora = datetime.now(TZ_MANAUS).replace(tzinfo=None)  # hora local de Manaus (ver docstring)
    hoje = agora.date()

    row = (
        await db.execute(
            text(
                """
                SELECT sh.id::text AS shift_id,
                       sh.post_id::text AS post_id,
                       sh.shift_date, sh.is_off_day, sh.status,
                       sh.employee_id::text AS employee_id,
                       sh.actual_start_time, sh.notes,
                       sh.planned_start_time, sh.planned_end_time,
                       e.nome, e.cargo
                FROM shifts sh
                LEFT JOIN employees e ON e.id = sh.employee_id
                WHERE sh.id = :sid
                """
            ),
            {"sid": shift_id},
        )
    ).first()

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turno não encontrado.")
    if post_ids is not None and row.post_id not in post_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Turno de posto fora do seu escopo.",
        )
    if row.shift_date != hoje:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Check-in manual só é permitido para turnos de HOJE.",
        )
    if row.employee_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Turno sem funcionário alocado — não há em quem registrar presença.",
        )
    if row.is_off_day or row.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Turno de folga ou cancelado não recebe check-in.",
        )

    # Já presente? (a) por batida real DENTRO da janela do turno (mesma regra do
    # quadro — batida da madrugada = saída do noturno de ontem, não conflita),
    # (b) por check-in manual anterior
    janela_ini, janela_fim = _janela_presenca(hoje, row.planned_start_time, row.planned_end_time)
    batida = (
        await db.execute(
            text(
                f"""
                SELECT MIN((cp.punch_timestamp))
                FROM gp_clock_punches cp
                WHERE cp.employee_id = :emp
                  AND (cp.punch_timestamp) >= :ini
                  AND (cp.punch_timestamp) <= :fim
                  AND {_PUNCH_VALIDO}
                """
            ),
            {"emp": row.employee_id, "ini": janela_ini, "fim": janela_fim},
        )
    ).scalar()
    if batida is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Funcionário já presente por batida de ponto às {batida.strftime('%H:%M')}.",
        )
    if row.actual_start_time is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Turno já tem check-in manual registrado.",
        )

    # Autoria no notes do shift (append, nunca sobrescreve histórico)
    autor = scope.user_name or scope.user_id
    observacao = (payload.observacao or "").strip() if payload else ""
    nota = f"[{agora.strftime('%d/%m/%Y %H:%M')}] check-in manual por {autor}"
    if observacao:
        nota += f" — {observacao}"
    notes = f"{row.notes}\n{nota}" if row.notes else nota

    await db.execute(
        text(
            """
            UPDATE shifts
            SET actual_start_time = :agora,
                status = 'in_progress',
                notes = :notes,
                updated_at = NOW()
            WHERE id = :sid
            """
        ),
        {"agora": agora, "notes": notes, "sid": shift_id},
    )
    await db.commit()

    logger.info(
        "Check-in manual registrado",
        action="presenca_checkin_manual",
        user_id=scope.user_id,
        shift_id=shift_id,
        employee_id=row.employee_id,
    )

    return FuncionarioTurno(
        employee_id=row.employee_id,
        nome=row.nome or "",
        cargo=row.cargo,
        shift_id=row.shift_id,
        turno_inicio=row.planned_start_time,
        turno_fim=row.planned_end_time,
        status="presente",
        presenca_em=agora,
        fonte="manual",
        facial_match=None,
        dentro_geofence=None,
    )
