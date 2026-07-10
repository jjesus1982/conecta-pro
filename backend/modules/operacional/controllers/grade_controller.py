"""
Editor de GRADE POR PESSOA (Operacional).

Permite ao gestor (Gonzaga/Paiva/Jordan) redesenhar a escala de UM colaborador
sem regenerar o posto inteiro: trocar turno (diurno/noturno), alternância
(dias pares/ímpares 12x36) ou padrão (12x36 ↔ comercial 44h), e encaixar
recém-admitidos na grade (ex.: Alexandre Silva no Mirante).

Rotas (montadas sob /api/v1/operacional):
- GET    /grade/postos                                → postos do escopo p/ seletor
- GET    /grade/{post_id}?mes&ano                     → grade por pessoa do posto
- PUT    /grade/{post_id}/colaborador                 → redesenha grade de 1 pessoa
- POST   /grade/{post_id}/colaborador                 → adiciona pessoa à grade
- DELETE /grade/{post_id}/colaborador/{employee_id}   → encerra pessoa na grade

REGRAS (alinhadas à task gerar_escalas_proximo_mes — mesma matemática):
- 12x36: trabalha nos dias do mês com a paridade escolhida (pares/ímpares).
  Meses de 31 dias INVERTEM a paridade no mês seguinte (alternância física
  contínua: quem trabalha dia 31 folga dia 1).
- Comercial 44h: seg-sex 8h (span de 9h c/ almoço), sábado 4h, domingo folga.
- Só o FUTURO é redesenhado (>= a_partir_de); turno com presença registrada
  nunca é tocado. Turnos antigos viram 'cancelled' com nota de autoria (audit).
- Férias aprovadas no DP são respeitadas: dias dentro de férias são PULADOS.
- Conflito (turno ativo em OUTRO posto no mesmo dia) → 409 com a lista, nada
  é gravado (tudo-ou-nada).
- Escrita é de GESTOR (scope.all_posts); líder só visualiza o próprio posto.
- Alocação nova só é criada com criar_alocacao=true explícito do usuário
  (alocações são curadas à mão pelo Jordan — a UI registra a autoria).

Timezone: shifts.planned_* e shift_date são hora LOCAL de Manaus (naive).
"""

import calendar
import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.logging import logger
from modules.operacional.scope import (
    OperationalScope,
    get_operational_scope,
    scope_post_ids_or_403,
)

router = APIRouter(prefix="/grade", tags=["Operacional - Grade por pessoa"])

TZ_MANAUS = ZoneInfo("America/Manaus")

HORARIOS_PADRAO = {
    ("12x36", "diurno"): (time(7, 0), time(19, 0)),
    ("12x36", "noturno"): (time(19, 0), time(7, 0)),
    ("comercial", "diurno"): (time(8, 0), None),  # fim calculado (span 9h / sáb 4h)
}

FERIAS_STATUS = ("APPROVED", "IN_PROGRESS", "SCHEDULED")


def _hoje_manaus() -> date:
    return datetime.now(TZ_MANAUS).date()


class GradeColaboradorBody(BaseModel):
    employee_id: str
    a_partir_de: date
    padrao: str = Field(pattern="^(12x36|comercial)$")
    turno: str = Field(default="diurno", pattern="^(diurno|noturno)$")
    paridade: str | None = Field(default=None, pattern="^(pares|impares)$")
    inicio: str | None = Field(default=None, description="HH:MM opcional; senão padrão do turno")
    fim_de_semana: str = Field(
        default="sabado",
        pattern="^(sabado|domingo|nenhum)$",
        description="Comercial 44h: qual dia de fim de semana a pessoa cobre (4h). Ex.: Mirante tem 2 ASG no sábado e 1 no domingo.",
    )
    inicio_fds: str | None = Field(
        default=None,
        description="HH:MM do dia de fim de semana quando difere da semana (ex.: Vanderlice abre o sábado 12:00–16:00). Default: mesmo início da semana.",
    )
    pausa_minutos: int | None = Field(
        default=None,
        ge=0,
        le=120,
        description="Intervalo do turno 12x36 em minutos. 0 = intrajornada paga/suprimida (ex.: Mirante); default 60 (ex.: Laranjeiras tem 1h de intervalo).",
    )
    criar_alocacao: bool = False
    setor: str | None = None


def _so_gestor(scope: OperationalScope) -> None:
    if not scope.all_posts:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Redesenhar a grade é ação de gestor. Líder de posto apenas visualiza.",
        )


def _post_no_escopo(scope: OperationalScope, post_id: str) -> None:
    pids = scope_post_ids_or_403(scope)
    if pids is not None and post_id not in pids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Posto fora do seu escopo.")


async def _post_ou_404(db: AsyncSession, post_id: str) -> dict:
    try:
        uuid.UUID(post_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Posto não encontrado.")
    row = (
        await db.execute(
            text("SELECT id::text, name FROM posts WHERE id=CAST(:p AS uuid) AND is_active"),
            {"p": post_id},
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Posto não encontrado.")
    return {"id": row[0], "name": row[1]}


@router.get("/postos")
async def grade_postos(
    scope: OperationalScope = Depends(get_operational_scope),
    db: AsyncSession = Depends(get_db),
):
    """Postos ativos do escopo, com nº de pessoas na grade do mês corrente."""
    pids = scope_post_ids_or_403(scope)
    hoje = _hoje_manaus()
    sql = """
        SELECT p.id::text, p.name,
               (SELECT count(DISTINCT s.employee_id) FROM shifts s
                 JOIN scales sc ON sc.id=s.scale_id AND sc.month=:m AND sc.year=:a
                WHERE s.post_id=p.id AND s.status='scheduled' AND s.is_active
                  AND s.employee_id IS NOT NULL) AS pessoas
        FROM posts p
        WHERE p.is_active AND p.status='active'
    """
    params: dict = {"m": hoje.month, "a": hoje.year}
    if pids is not None:
        sql += " AND p.id = ANY(CAST(:pids AS uuid[]))"
        params["pids"] = pids
    sql += " ORDER BY p.name"
    rows = (await db.execute(text(sql), params)).all()
    return {
        "mes": hoje.month,
        "ano": hoje.year,
        "somente_leitura": not scope.all_posts,
        "postos": [{"post_id": r[0], "post_nome": r[1], "pessoas_na_grade": int(r[2])} for r in rows],
    }


@router.get("/{post_id}")
async def grade_do_posto(
    post_id: str,
    mes: int | None = None,
    ano: int | None = None,
    scope: OperationalScope = Depends(get_operational_scope),
    db: AsyncSession = Depends(get_db),
):
    """Grade por pessoa do posto no mês: padrão derivado dos turnos REAIS agendados."""
    _post_no_escopo(scope, post_id)
    post = await _post_ou_404(db, post_id)
    hoje = _hoje_manaus()
    mes, ano = mes or hoje.month, ano or hoje.year

    pessoas = (
        await db.execute(
            text(
                """
                SELECT s.employee_id::text, e.nome, e.cargo,
                       max(s.planned_hours) AS horas,
                       bool_or(s.is_night_shift) AS noturno,
                       mode() WITHIN GROUP (ORDER BY s.planned_start_time) AS inicio,
                       mode() WITHIN GROUP (ORDER BY s.planned_end_time) AS fim,
                       mode() WITHIN GROUP (ORDER BY (EXTRACT(DAY FROM s.shift_date)::int % 2)) AS paridade,
                       count(*) AS n_turnos,
                       array_agg(EXTRACT(DAY FROM s.shift_date)::int ORDER BY s.shift_date) AS dias,
                       bool_or(EXTRACT(DOW FROM s.shift_date) = 6) AS trabalha_sab,
                       bool_or(EXTRACT(DOW FROM s.shift_date) = 0) AS trabalha_dom
                FROM shifts s
                JOIN scales sc ON sc.id = s.scale_id AND sc.month=:m AND sc.year=:a
                JOIN employees e ON e.id = s.employee_id
                WHERE s.post_id=CAST(:p AS uuid) AND s.status='scheduled' AND s.is_active
                  AND s.employee_id IS NOT NULL
                GROUP BY s.employee_id, e.nome, e.cargo
                ORDER BY e.nome
                """
            ),
            {"p": post_id, "m": mes, "a": ano},
        )
    ).all()

    emp_ids = [r[0] for r in pessoas]
    ferias_map: dict[str, list] = {}
    if emp_ids:
        for eid, ini, fim in (
            await db.execute(
                text(
                    """
                    SELECT employee_id::text, start_date, end_date FROM hr_vacation_requests
                    WHERE employee_id = ANY(CAST(:ids AS uuid[]))
                      AND upper(status) IN ('APPROVED','IN_PROGRESS','SCHEDULED')
                      AND start_date <= :fim_mes AND end_date >= :ini_mes
                    """
                ),
                {"ids": emp_ids, "ini_mes": date(ano, mes, 1),
                 "fim_mes": date(ano, mes, calendar.monthrange(ano, mes)[1])},
            )
        ).all():
            ferias_map.setdefault(eid, []).append({"inicio": str(ini), "fim": str(fim)})

    # Alocados ativos no posto SEM turno agendado no mês (candidatos a entrar na grade)
    sem_grade = (
        await db.execute(
            text(
                """
                SELECT e.id::text, e.nome, e.cargo
                FROM allocations a
                JOIN employees e ON e.id=a.employee_id AND e.status='ativo'
                WHERE a.post_id=CAST(:p AS uuid) AND a.status='active' AND a.is_active
                  AND NOT EXISTS (
                    SELECT 1 FROM shifts s JOIN scales sc ON sc.id=s.scale_id AND sc.month=:m AND sc.year=:a
                    WHERE s.employee_id=e.id AND s.post_id=a.post_id
                      AND s.status='scheduled' AND s.is_active)
                ORDER BY e.nome
                """
            ),
            {"p": post_id, "m": mes, "a": ano},
        )
    ).all()

    def _tipo(horas, inicio) -> dict:
        # turno derivado do horário-moda REAL (>=15h = noturno), não da flag is_night
        # acumulada (bool_or pega histórico antigo de quem trocou de turno no mês)
        if float(horas) >= 12:
            return {"padrao": "12x36", "turno": "noturno" if inicio.hour >= 15 else "diurno"}
        return {"padrao": "comercial", "turno": "diurno"}

    return {
        "post_id": post["id"],
        "post_nome": post["name"],
        "mes": mes,
        "ano": ano,
        "somente_leitura": not scope.all_posts,
        "pessoas": [
            {
                "employee_id": r[0],
                "nome": r[1],
                "cargo": r[2],
                **_tipo(r[3], r[5]),
                "inicio": str(r[5])[:5],
                "fim": str(r[6])[:5],
                "paridade": ("impares" if int(r[7]) == 1 else "pares") if float(r[3]) >= 12 else None,
                "fim_de_semana": (
                    None if float(r[3]) >= 12
                    else "domingo" if r[11] else "sabado" if r[10] else "nenhum"
                ),
                "turnos_no_mes": int(r[8]),
                "dias": list(r[9]),
                "ferias": ferias_map.get(r[0], []),
            }
            for r in pessoas
        ],
        "sem_grade": [{"employee_id": r[0], "nome": r[1], "cargo": r[2]} for r in sem_grade],
    }


def _dias_de_trabalho(
    ano: int, mes: int, desde: date | None, padrao: str, paridade_alvo: int | None,
    fim_de_semana: str = "sabado",
) -> list[date]:
    """Dias em que a pessoa trabalha no mês, pela mesma matemática da geração automática.
    Comercial 44h: seg-sex sempre; do fim de semana, só o dia que a pessoa cobre
    (sábado OU domingo, 4h) — ex.: Mirante tem 2 ASG no sábado e 1 no domingo."""
    dias = []
    for d in range(1, calendar.monthrange(ano, mes)[1] + 1):
        dia = date(ano, mes, d)
        if desde and dia < desde:
            continue
        if padrao == "12x36":
            if d % 2 == paridade_alvo:
                dias.append(dia)
        else:  # comercial 44h
            dow = dia.weekday()
            if dow < 5:
                dias.append(dia)
            elif dow == 5 and fim_de_semana == "sabado":
                dias.append(dia)
            elif dow == 6 and fim_de_semana == "domingo":
                dias.append(dia)
    return dias


async def _aplicar_grade(
    db: AsyncSession, post: dict, body: GradeColaboradorBody, user_name: str, user_id: str
) -> dict:
    """Núcleo compartilhado do PUT/POST: valida, cancela o futuro e regenera. Tudo-ou-nada."""
    hoje = _hoje_manaus()
    if body.a_partir_de < hoje:
        raise HTTPException(status_code=422, detail="a_partir_de não pode ser no passado — o histórico é fato, não plano.")
    if body.padrao == "12x36" and not body.paridade:
        raise HTTPException(status_code=422, detail="Para 12x36 informe a alternância (pares/impares).")

    emp = (
        await db.execute(
            text("SELECT id::text, nome, cargo FROM employees WHERE id=CAST(:e AS uuid) AND status='ativo'"),
            {"e": body.employee_id},
        )
    ).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado ou não está ativo.")

    # Horários
    if body.padrao == "12x36":
        ini_pad, fim_pad = HORARIOS_PADRAO[("12x36", body.turno)]
    else:
        ini_pad, fim_pad = HORARIOS_PADRAO[("comercial", "diurno")]
    if body.inicio:
        try:
            h, m = body.inicio.split(":")
            ini_pad = time(int(h), int(m))
        except (ValueError, AttributeError):
            raise HTTPException(status_code=422, detail="inicio inválido — use HH:MM.")
        if body.padrao == "12x36":
            fim_pad = (datetime.combine(hoje, ini_pad) + timedelta(hours=12)).time()
    ini_fds = ini_pad
    if body.inicio_fds:
        try:
            h, m = body.inicio_fds.split(":")
            ini_fds = time(int(h), int(m))
        except (ValueError, AttributeError):
            raise HTTPException(status_code=422, detail="inicio_fds inválido — use HH:MM.")

    # Meses do horizonte: o mês de a_partir_de + meses FUTUROS que já têm escala no posto
    m0, a0 = body.a_partir_de.month, body.a_partir_de.year
    escalas = (
        await db.execute(
            text(
                """
                SELECT id::text, month, year FROM scales
                WHERE post_id=CAST(:p AS uuid) AND is_active
                  AND (year > :a OR (year = :a AND month >= :m))
                ORDER BY year, month
                """
            ),
            {"p": post["id"], "m": m0, "a": a0},
        )
    ).all()
    if not escalas or (escalas[0][1], escalas[0][2]) != (m0, a0):
        raise HTTPException(
            status_code=422,
            detail=f"O posto não tem escala para {m0:02d}/{a0} — gere/publique a escala do mês antes de editar a grade.",
        )

    # Paridade por mês (12x36): meses de 31 dias invertem a do mês seguinte
    paridade_alvo = None
    if body.padrao == "12x36":
        paridade_alvo = 0 if body.paridade == "pares" else 1

    plano: list[tuple[str, list[date]]] = []  # (scale_id, dias) por mês
    par = paridade_alvo
    mes_ant, ano_ant = m0, a0
    for scale_id, mm, aa in escalas:
        if (mm, aa) != (m0, a0) and body.padrao == "12x36":
            # aplica viradas de paridade acumuladas entre mes_ant e mm
            while (mes_ant, ano_ant) != (mm, aa):
                if calendar.monthrange(ano_ant, mes_ant)[1] % 2 == 1:
                    par = 1 - par
                mes_ant = 1 if mes_ant == 12 else mes_ant + 1
                ano_ant = ano_ant + 1 if mes_ant == 1 else ano_ant
        desde = body.a_partir_de if (mm, aa) == (m0, a0) else None
        plano.append((scale_id, _dias_de_trabalho(aa, mm, desde, body.padrao, par, body.fim_de_semana)))

    todos_dias = [d for _, dias in plano for d in dias]
    # Horizonte de CANCELAMENTO = fim do último mês com escala (não o último dia do novo
    # plano): quando a paridade vira para 'pares', o plano termina dia 30 e um turno antigo
    # de dia 31 sobreviveria órfão (bug corrigido em 10/07 — caso Eduardo 31/08).
    _, ult_m, ult_a = escalas[-1]
    fim_horizonte = date(ult_a, ult_m, calendar.monthrange(ult_a, ult_m)[1])

    # Férias aprovadas → dias pulados (nunca sobrepor férias do DP)
    ferias = (
        await db.execute(
            text(
                """
                SELECT start_date, end_date FROM hr_vacation_requests
                WHERE employee_id=CAST(:e AS uuid) AND upper(status) IN ('APPROVED','IN_PROGRESS','SCHEDULED')
                  AND start_date <= :fim AND end_date >= :ini
                """
            ),
            {"e": body.employee_id, "ini": body.a_partir_de, "fim": fim_horizonte},
        )
    ).all()
    em_ferias = {d for ini, fim in ferias for d in todos_dias if ini <= d <= fim}

    # Conflito: turno ativo em OUTRO posto num dia do plano → 409, nada gravado
    dias_uteis = [d for d in todos_dias if d not in em_ferias]
    if dias_uteis:
        conflitos = (
            await db.execute(
                text(
                    """
                    SELECT s.shift_date, p.name FROM shifts s JOIN posts p ON p.id=s.post_id
                    WHERE s.employee_id=CAST(:e AS uuid) AND s.is_active AND NOT s.is_off_day
                      AND s.status IN ('scheduled','in_progress')
                      AND s.post_id <> CAST(:p AS uuid)
                      AND s.shift_date = ANY(CAST(:dias AS date[]))
                    ORDER BY s.shift_date
                    """
                ),
                {"e": body.employee_id, "p": post["id"], "dias": dias_uteis},
            )
        ).all()
        if conflitos:
            raise HTTPException(
                status_code=409,
                detail={
                    "mensagem": f"{emp[1]} já tem turno em outro posto em {len(conflitos)} dia(s) do novo padrão. Nada foi alterado.",
                    "conflitos": [{"dia": str(c[0]), "posto": c[1]} for c in conflitos[:20]],
                },
            )

    autoria = f"Grade por pessoa: redesenhada por {user_name} em {hoje.isoformat()}"

    # Cancela o plano FUTURO antigo desta pessoa neste posto (nunca toca presença registrada)
    cancelados = (
        await db.execute(
            text(
                """
                UPDATE shifts SET status='cancelled', needs_substitution=false,
                       notes=COALESCE(notes,'') || ' | ' || :aut, updated_at=now()
                WHERE employee_id=CAST(:e AS uuid) AND post_id=CAST(:p AS uuid)
                  AND shift_date >= :desde AND shift_date <= :fim
                  AND status='scheduled' AND is_active AND actual_start_time IS NULL
                """
            ),
            {"e": body.employee_id, "p": post["id"], "desde": body.a_partir_de,
             "fim": fim_horizonte, "aut": autoria},
        )
    ).rowcount

    criados = 0
    for scale_id, dias in plano:
        for dia in dias:
            if dia in em_ferias:
                continue
            ini_d = ini_pad
            if body.padrao == "12x36":
                pausa_12 = 60 if body.pausa_minutos is None else body.pausa_minutos
                h, pausa, fim_d, is_n = 12.0, pausa_12, fim_pad, body.turno == "noturno"
            else:
                if dia.weekday() >= 5:  # dia de fim de semana coberto (sáb OU dom): 4h
                    h, pausa, ini_d = 4.0, 0, ini_fds
                    fim_d = (datetime.combine(dia, ini_fds) + timedelta(hours=4)).time()
                else:  # seg-sex 8h, span 9h com almoço
                    h, pausa = 8.0, 60
                    fim_d = (datetime.combine(dia, ini_pad) + timedelta(hours=9)).time()
                is_n = False
            await db.execute(
                text(
                    """
                    INSERT INTO shifts (id, scale_id, employee_id, post_id, shift_date,
                        planned_start_time, planned_end_time, planned_break_minutes, status,
                        is_holiday, is_night_shift, is_overtime, is_off_day, needs_substitution,
                        planned_hours, actual_hours, overtime_hours, night_hours, base_pay,
                        overtime_pay, night_bonus, holiday_bonus, total_pay, notes, is_active,
                        created_at, updated_at)
                    VALUES (CAST(:id AS uuid), CAST(:sc AS uuid), CAST(:emp AS uuid),
                        CAST(:post AS uuid), :dia, :ini, :fim, :pausa, 'scheduled',
                        false, :noturno, false, false, false, :h, 0,0,0,0,0,0,0,0,
                        :nota, true, now(), now())
                    """
                ),
                {"id": str(uuid.uuid4()), "sc": scale_id, "emp": body.employee_id,
                 "post": post["id"], "dia": dia, "ini": ini_d, "fim": fim_d,
                 "pausa": pausa, "noturno": is_n, "h": h, "nota": autoria},
            )
            criados += 1
        await db.execute(
            text(
                """
                UPDATE scales s SET total_shifts=q.n, filled_shifts=q.n, total_hours=q.h, updated_at=now()
                FROM (SELECT count(*) n, COALESCE(sum(planned_hours),0) h FROM shifts
                      WHERE scale_id=CAST(:sc AS uuid) AND is_active AND status='scheduled') q
                WHERE s.id=CAST(:sc AS uuid)
                """
            ),
            {"sc": scale_id},
        )

    await db.commit()
    logger.info(
        f"[grade] {user_name} redesenhou {emp[1]} no posto {post['name']}: "
        f"{body.padrao}/{body.turno}/{body.paridade or '-'} a partir de {body.a_partir_de} "
        f"({cancelados} cancelados, {criados} criados)"
    )
    return {
        "ok": True,
        "colaborador": {"employee_id": emp[0], "nome": emp[1], "cargo": emp[2]},
        "posto": post["name"],
        "padrao": body.padrao,
        "turno": body.turno,
        "paridade": body.paridade,
        "a_partir_de": str(body.a_partir_de),
        "turnos_cancelados": cancelados,
        "turnos_criados": criados,
        "dias_pulados_por_ferias": len(em_ferias),
        "meses_afetados": [f"{mm:02d}/{aa}" for _, mm, aa in escalas],
    }


@router.put("/{post_id}/colaborador")
async def redesenhar_grade_colaborador(
    post_id: str,
    body: GradeColaboradorBody,
    scope: OperationalScope = Depends(get_operational_scope),
    db: AsyncSession = Depends(get_db),
):
    """Redesenha a grade de UMA pessoa já alocada no posto (turno/alternância/padrão)."""
    _so_gestor(scope)
    post = await _post_ou_404(db, post_id)
    aloc = (
        await db.execute(
            text(
                """SELECT 1 FROM allocations WHERE employee_id=CAST(:e AS uuid)
                   AND post_id=CAST(:p AS uuid) AND status='active' AND is_active"""
            ),
            {"e": body.employee_id, "p": post_id},
        )
    ).first()
    if not aloc:
        raise HTTPException(
            status_code=422,
            detail="Colaborador não tem alocação ativa neste posto. Use o fluxo de ADICIONAR à grade (com criar_alocacao).",
        )
    return await _aplicar_grade(db, post, body, scope.user_name or "gestor", scope.user_id)


@router.post("/{post_id}/colaborador", status_code=status.HTTP_201_CREATED)
async def adicionar_colaborador_na_grade(
    post_id: str,
    body: GradeColaboradorBody,
    scope: OperationalScope = Depends(get_operational_scope),
    db: AsyncSession = Depends(get_db),
):
    """Encaixa uma pessoa NOVA na grade do posto (ex.: recém-admitido). Cria a
    alocação apenas com criar_alocacao=true explícito (autoria registrada)."""
    _so_gestor(scope)
    post = await _post_ou_404(db, post_id)
    aloc = (
        await db.execute(
            text(
                """SELECT 1 FROM allocations WHERE employee_id=CAST(:e AS uuid)
                   AND post_id=CAST(:p AS uuid) AND status='active' AND is_active"""
            ),
            {"e": body.employee_id, "p": post_id},
        )
    ).first()
    alocacao_criada = False
    if not aloc:
        if not body.criar_alocacao:
            raise HTTPException(
                status_code=422,
                detail="Sem alocação ativa neste posto. Confirme criar_alocacao=true para alocar e escalar.",
            )
        await db.execute(
            text(
                """
                INSERT INTO allocations (id, post_id, employee_id, status, start_date,
                    is_primary, is_temporary, hourly_rate, monthly_salary, additional_benefits,
                    setor, notes, is_active, created_at, updated_at, created_by)
                VALUES (CAST(:id AS uuid), CAST(:p AS uuid), CAST(:e AS uuid), 'active', :ini,
                    true, false, 0, 0, 0, :setor,
                    :nota, true, now(), now(), CAST(:u AS uuid))
                """
            ),
            {"id": str(uuid.uuid4()), "p": post_id, "e": body.employee_id,
             "ini": body.a_partir_de, "setor": (body.setor or "PORTARIA").upper(),
             "nota": f"Criada pelo editor de grade por {scope.user_name} em {_hoje_manaus().isoformat()}",
             "u": scope.user_id},
        )
        alocacao_criada = True
    resultado = await _aplicar_grade(db, post, body, scope.user_name or "gestor", scope.user_id)
    resultado["alocacao_criada"] = alocacao_criada
    return resultado


@router.delete("/{post_id}/colaborador/{employee_id}")
async def encerrar_colaborador_na_grade(
    post_id: str,
    employee_id: str,
    a_partir_de: date,
    scope: OperationalScope = Depends(get_operational_scope),
    db: AsyncSession = Depends(get_db),
):
    """Encerra a pessoa na grade: cancela os turnos FUTUROS dela no posto a partir
    da data. NÃO mexe na alocação nem no cadastro (isso é do DP/Jordan)."""
    _so_gestor(scope)
    post = await _post_ou_404(db, post_id)
    hoje = _hoje_manaus()
    if a_partir_de < hoje:
        raise HTTPException(status_code=422, detail="a_partir_de não pode ser no passado.")
    autoria = f"Encerrado na grade por {scope.user_name} em {hoje.isoformat()}"
    cancelados = (
        await db.execute(
            text(
                """
                UPDATE shifts SET status='cancelled', needs_substitution=false,
                       notes=COALESCE(notes,'') || ' | ' || :aut, updated_at=now()
                WHERE employee_id=CAST(:e AS uuid) AND post_id=CAST(:p AS uuid)
                  AND shift_date >= :desde AND status='scheduled' AND is_active
                  AND actual_start_time IS NULL
                """
            ),
            {"e": employee_id, "p": post_id, "desde": a_partir_de, "aut": autoria},
        )
    ).rowcount
    await db.commit()
    logger.info(f"[grade] {scope.user_name} encerrou {employee_id} na grade de {post['name']}: {cancelados} turnos cancelados")
    return {"ok": True, "posto": post["name"], "turnos_cancelados": cancelados, "a_partir_de": str(a_partir_de)}
