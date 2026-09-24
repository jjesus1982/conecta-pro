"""Cobertura — quem cobriu quem, em que posto, por quanto tempo, e se foi FOLGA TRABALHADA
(paridade DGX, F8 — `/frontend/coberturas/index`: Colaborador Coberto · Colaborador Cobertura ·
Data Início/Término · Motivo · Folga Trabalhada).

Fonte: `substitutions` — a mesma tabela do fluxo falta → substituto do quadro de presença
(`falta_substituto_controller`). Uma cobertura de período vira UMA LINHA POR DIA (é assim que o
turno existe: `shifts` é diário), amarradas por `cobertura_id`. Cada dia grava:

  · `folga_trabalhada` — derivado de `shifts` do COBERTURA naquele dia, ANTES de criar o turno
    espelho: tinha linha `is_off_day`, ou não tinha turno nenhum no dia mas tem escala na
    quinzena em volta (12x36: o dia de folga não tem linha). Quem não tem escala nenhuma (volante)
    não está "de folga" — fica false. O oráculo reconta com SQL próprio.
  · `horas` — `planned_hours` do turno de referência (o do coberto no dia; senão o último do
    coberto no posto; senão o horário padrão do posto). Sem referência = 422, nunca inventa.
  · `shift_cobertura_id` — o turno espelho criado para o cobertura (mesmo INSERT do
    `escalar_substituto`), para a grade/presença enxergar quem está no posto.
  · `alocacao_id` — cobertura de FÉRIAS/AFASTAMENTO também vira movimentação da F5
    (`movimentacao_service.alocar`, motivo `cobertura_de_*`), com `data_fim` = término.

Regras: coberto ≠ cobertura; ambos ativos; período ≤ 62 dias e dentro de ±60 dias de hoje;
cobertura com turno (não folga) no dia → 409, nunca dois postos no mesmo dia (mesma régua do
quadro). Motivo falta/atestado marca o turno do coberto como `missed` (como `registrar_falta`).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text

from modules.operacional.services import movimentacao_service as ms

# DGX: Volante · Férias · Falta · Afastamento · Atestado · Folga · Atividade Externa → `reason`
# (varchar 50; os 3 primeiros usam os valores que `SubstitutionReason` já tinha).
MOTIVOS = {
    "falta": "no_show",
    "atestado": "sick_leave",
    "ferias": "vacation",
    "afastamento": "afastamento",
    "folga": "folga",
    "volante": "volante",
    "atividade_externa": "atividade_externa",
}
ROTULO = {
    "no_show": "Falta",
    "sick_leave": "Atestado",
    "vacation": "Férias",
    "afastamento": "Afastamento",
    "folga": "Folga",
    "volante": "Volante",
    "atividade_externa": "Atividade externa",
    "personal": "Pessoal",
    "training": "Treinamento",
    "emergency": "Emergência",
    "other": "Outro",
}
MOTIVO_F5 = {"ferias": "cobertura_de_ferias", "afastamento": "cobertura_de_afastamento"}
MARCA_FALTA = ("falta", "atestado")
LIMITE_DIAS = 62
JANELA_DIAS = 60
JANELA_ESCALA_DIAS = 15  # "tem escala na quinzena em volta" → dia sem turno é folga

_DDL = [
    # cobertura de férias/afastamento pode cair em dia sem turno do coberto (a escala não gera
    # turno para quem está de férias) — a linha existe mesmo assim, sem shift de origem
    "ALTER TABLE substitutions ALTER COLUMN shift_id DROP NOT NULL",
    "ALTER TABLE substitutions ADD COLUMN IF NOT EXISTS cobertura_id uuid",
    "ALTER TABLE substitutions ADD COLUMN IF NOT EXISTS folga_trabalhada boolean",
    "ALTER TABLE substitutions ADD COLUMN IF NOT EXISTS horas numeric(5,2)",
    "ALTER TABLE substitutions ADD COLUMN IF NOT EXISTS shift_cobertura_id uuid",
    "ALTER TABLE substitutions ADD COLUMN IF NOT EXISTS alocacao_id uuid",
    "CREATE INDEX IF NOT EXISTS ix_substitutions_cobertura ON substitutions (cobertura_id)",
]

SQL_TURNO_DO_DIA = """
SELECT s.id::text, s.scale_id::text, s.planned_start_time, s.planned_end_time, s.planned_break_minutes,
       s.planned_hours, s.is_night_shift, s.status
FROM shifts s WHERE s.employee_id = CAST(:e AS uuid) AND s.shift_date = :d AND s.is_active
  AND NOT s.is_off_day AND s.status <> 'cancelled' AND s.post_id = CAST(:p AS uuid)
ORDER BY s.planned_start_time LIMIT 1
"""
SQL_ULTIMO_TURNO_NO_POSTO = """
SELECT s.id::text, s.scale_id::text, s.planned_start_time, s.planned_end_time, s.planned_break_minutes,
       s.planned_hours, s.is_night_shift, s.status
FROM shifts s WHERE s.employee_id = CAST(:e AS uuid) AND s.post_id = CAST(:p AS uuid) AND s.is_active
  AND NOT s.is_off_day AND s.status <> 'cancelled' AND s.shift_date BETWEEN CAST(:d AS date) - 60 AND CAST(:d AS date) + 60
ORDER BY abs(s.shift_date - CAST(:d AS date)) LIMIT 1
"""
SQL_PADRAO_DO_POSTO = """
SELECT p.shift_start_time, p.shift_end_time, coalesce(p.break_duration_minutes, 60),
       (SELECT sc.id::text FROM scales sc WHERE sc.post_id = p.id AND coalesce(sc.is_active, true)
         ORDER BY sc.year DESC, sc.month DESC LIMIT 1)
FROM posts p WHERE p.id = CAST(:p AS uuid)
"""
SQL_CONFLITO = """
SELECT p.name FROM shifts s JOIN posts p ON p.id = s.post_id
WHERE s.employee_id = CAST(:e AS uuid) AND s.is_active AND NOT s.is_off_day
  AND s.status IN ('scheduled', 'in_progress', 'completed')
  AND (s.shift_date = :d OR (s.shift_date = CAST(:d AS date) - 1 AND s.planned_end_time <= s.planned_start_time))
LIMIT 1
"""
# folga trabalhada: linha is_off_day no dia, OU nenhum turno no dia mas escala na quinzena em volta
SQL_FOLGA = """
SELECT (EXISTS (SELECT 1 FROM shifts s WHERE s.employee_id = CAST(:e AS uuid) AND s.shift_date = :d
                 AND s.is_active AND s.is_off_day))
    OR (NOT EXISTS (SELECT 1 FROM shifts s WHERE s.employee_id = CAST(:e AS uuid) AND s.shift_date = :d
                     AND s.is_active AND NOT s.is_off_day AND s.status <> 'cancelled')
        AND EXISTS (SELECT 1 FROM shifts s WHERE s.employee_id = CAST(:e AS uuid) AND s.is_active
                     AND NOT s.is_off_day AND s.status <> 'cancelled'
                     AND s.shift_date BETWEEN CAST(:d AS date) - CAST(:j AS integer) AND CAST(:d AS date) + CAST(:j AS integer)))
"""


class CoberturaErro(ValueError):  # noqa: N818 — nome em PT-BR, padrão da casa
    def __init__(self, status: int, msg: str) -> None:
        super().__init__(msg)
        self.status = status


def hoje_manaus() -> date:
    return datetime.now(ZoneInfo("America/Manaus")).date()


def agora_manaus() -> datetime:
    return datetime.now(ZoneInfo("America/Manaus")).replace(tzinfo=None)


async def _ensure(db) -> None:
    for sql in _DDL:
        await db.execute(text(sql))
    await db.commit()


def _data(v) -> date:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise CoberturaErro(400, f"Data inválida: {v!r} (use AAAA-MM-DD).") from None


async def _ativo(db, employee_id: str) -> tuple[str, str]:
    row = (
        await db.execute(
            text("SELECT nome, coalesce(cargo,'') FROM employees WHERE id = CAST(:e AS uuid) AND status = 'ativo'"),
            {"e": employee_id},
        )
    ).fetchone()
    if not row:
        raise CoberturaErro(404, "Colaborador não encontrado ou não está ativo.")
    return row[0], row[1]


async def _referencia(db, coberto: str, post_id: str, dia: date) -> dict:
    """Turno de referência do dia: o do coberto no posto; senão o mais próximo dele no posto;
    senão o horário padrão do posto. Sem nada → 422 (nunca fabrica horário)."""
    r = (await db.execute(text(SQL_TURNO_DO_DIA), {"e": coberto, "d": dia, "p": post_id})).fetchone()
    proprio = r is not None
    if r is None:
        r = (await db.execute(text(SQL_ULTIMO_TURNO_NO_POSTO), {"e": coberto, "d": dia, "p": post_id})).fetchone()
    if r is not None:
        ini, fim = r[2], r[3]
        horas = float(r[5] or 0) or _horas(ini, fim, r[4] or 0)
        return {
            "shift_id": r[0] if proprio else None,
            "scale_id": r[1],
            "ini": ini,
            "fim": fim,
            "pausa": r[4] or 60,
            "horas": horas,
            "noturno": bool(r[6]),
            "status": r[7],
        }
    p = (await db.execute(text(SQL_PADRAO_DO_POSTO), {"p": post_id})).fetchone()
    if not p or not p[0] or not p[1] or not p[3]:
        raise CoberturaErro(
            422,
            f"Sem turno de referência em {dia:%d/%m/%Y}: o coberto não tem turno nesse posto e o posto não tem horário/escala padrão.",
        )
    return {
        "shift_id": None,
        "scale_id": p[3],
        "ini": p[0],
        "fim": p[1],
        "pausa": p[2],
        "horas": _horas(p[0], p[1], p[2]),
        "noturno": p[0].hour >= 15,
        "status": None,
    }


def _horas(ini, fim, pausa: int) -> float:
    a = ini.hour * 60 + ini.minute
    b = fim.hour * 60 + fim.minute
    if b <= a:
        b += 24 * 60
    return round((b - a - (pausa or 0)) / 60, 2)


async def folga_no_dia(db, employee_id: str, dia: date) -> bool:
    return bool((await db.execute(text(SQL_FOLGA), {"e": employee_id, "d": dia, "j": JANELA_ESCALA_DIAS})).scalar())


async def registrar(
    db,
    *,
    coberto_id: str,
    cobertura_id: str,
    post_id: str,
    inicio,
    fim=None,
    motivo: str,
    observacao: str | None = None,
    user_id: str | None = None,
    user_nome: str = "redesign",
) -> dict:
    """Registra a cobertura do período (uma linha de `substitutions` por dia + turno espelho).
    Férias/afastamento também alocam o cobertura no condomínio do posto (F5)."""
    await _ensure(db)
    ini = _data(inicio)
    ter = _data(fim) if fim else ini
    if motivo not in MOTIVOS:
        raise CoberturaErro(400, f"Motivo inválido: {motivo!r}. Use um de {', '.join(MOTIVOS)}.")
    if not coberto_id or not cobertura_id or not post_id:
        raise CoberturaErro(400, "Coberto, cobertura e posto são obrigatórios.")
    if coberto_id == cobertura_id:
        raise CoberturaErro(422, "O cobertura não pode ser o próprio coberto.")
    if ter < ini:
        raise CoberturaErro(422, f"Término ({ter:%d/%m/%Y}) anterior ao início ({ini:%d/%m/%Y}).")
    if (ter - ini).days + 1 > LIMITE_DIAS:
        raise CoberturaErro(422, f"Período maior que {LIMITE_DIAS} dias — registre em partes.")
    hoje = hoje_manaus()
    if ini < hoje - timedelta(days=JANELA_DIAS) or ter > hoje + timedelta(days=JANELA_DIAS):
        raise CoberturaErro(422, f"Período fora da janela de ±{JANELA_DIAS} dias de hoje.")
    nome_cob, cargo_cob = await _ativo(db, cobertura_id)
    nome_cbt, _ = await _ativo(db, coberto_id)
    posto = (
        await db.execute(
            text(
                "SELECT p.name, (SELECT c.id::text FROM condominios c WHERE c.client_id = p.client_id AND c.ativo LIMIT 1) "
                "FROM posts p WHERE p.id = CAST(:p AS uuid) AND p.is_active"
            ),
            {"p": post_id},
        )
    ).fetchone()
    if not posto:
        raise CoberturaErro(404, "Posto não encontrado ou inativo.")

    # 1ª passada: só valida (nada gravado se um dia falhar)
    dias: list[tuple[date, dict, bool]] = []
    d = ini
    while d <= ter:
        conflito = (await db.execute(text(SQL_CONFLITO), {"e": cobertura_id, "d": d})).scalar()
        if conflito:
            raise CoberturaErro(
                409, f"{nome_cob} já tem turno em {conflito} em {d:%d/%m/%Y} — nunca dois postos no mesmo dia."
            )
        ja = (
            await db.execute(
                text(
                    "SELECT 1 FROM substitutions WHERE original_employee_id = CAST(:c AS uuid) AND substitution_date = :d "
                    "AND is_active AND status IN ('pending','confirmed','in_progress','completed') AND post_id = CAST(:p AS uuid)"
                ),
                {"c": coberto_id, "d": d, "p": post_id},
            )
        ).scalar()
        if ja:
            raise CoberturaErro(409, f"{nome_cbt} já está coberto nesse posto em {d:%d/%m/%Y}.")
        ref = await _referencia(db, coberto_id, post_id, d)
        folga = await folga_no_dia(db, cobertura_id, d)  # ANTES do turno espelho existir
        dias.append((d, ref, folga))
        d += timedelta(days=1)

    agora = agora_manaus()
    grupo = str(uuid.uuid4())
    obs = (observacao or "").strip() or None
    reason = MOTIVOS[motivo]
    nota = f"COBERTURA ({ROTULO[reason]}): {nome_cob} cobre {nome_cbt} — registrado por {user_nome} em {agora:%d/%m %H:%M}."
    if obs:
        nota += f" {obs}"

    # F5 ANTES das linhas do dia: `ms.alocar` valida (coberto de férias aprovadas / afastamento
    # ativo) e COMMITA — se viesse depois, as linhas já estariam no banco quando ele recusasse.
    alocacao_id = None
    if motivo in MOTIVO_F5:
        if not posto[1]:
            raise CoberturaErro(422, "O posto não está ligado a um condomínio — a movimentação da F5 precisa dele.")
        try:
            r = await ms.alocar(
                db,
                employee_id=cobertura_id,
                condominio_id=posto[1],
                funcao=cargo_cob or "AGENTE DE PORTARIA",
                posto_id=post_id,
                data_inicio=ini,
                motivo=MOTIVO_F5[motivo],
                solicitado_por="supervisor",
                solicitante_nome=user_nome,
                coberto_employee_id=coberto_id,
                observacao=f"cobertura {grupo} · {obs or ''}".strip(" ·"),
                user_id=user_id,
            )
        except ms.MovimentacaoErro as exc:
            await db.rollback()
            raise CoberturaErro(exc.status, str(exc)) from exc
        alocacao_id = r["id"]
        await db.execute(
            text("UPDATE employee_alocacoes SET data_fim = :f WHERE id = CAST(:i AS uuid)"),
            {"f": ter, "i": alocacao_id},
        )

    ids: list[str] = []
    for d, ref, folga in dias:
        shift_esp = str(uuid.uuid4())
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
                    false, :noturno, :folga, false, false, :h, 0,0,0,0,0,0,0,0,
                    :nota, true, now(), now())
                """
            ),
            {
                "id": shift_esp,
                "sc": ref["scale_id"],
                "emp": cobertura_id,
                "post": post_id,
                "dia": d,
                "ini": ref["ini"],
                "fim": ref["fim"],
                "pausa": ref["pausa"],
                "noturno": ref["noturno"],
                "folga": folga,
                "h": ref["horas"],
                "nota": "SUBSTITUIÇÃO: " + nota,
            },
        )
        if ref["shift_id"]:
            await db.execute(
                text(
                    "UPDATE shifts SET needs_substitution=false, "
                    " status = CASE WHEN CAST(:falta AS boolean) AND status = 'scheduled' THEN 'missed' ELSE status END, "
                    " notes = concat_ws(' | ', notes, CAST(:n AS text)), updated_at = now() WHERE id = CAST(:s AS uuid)"
                ),
                {"falta": motivo in MARCA_FALTA, "n": nota, "s": ref["shift_id"]},
            )
        sid = str(uuid.uuid4())
        await db.execute(
            text(
                """
                INSERT INTO substitutions (id, shift_id, post_id, original_employee_id, substitute_employee_id,
                    reason, reason_details, status, substitution_date, requested_at, confirmed_at,
                    additional_cost, overtime_hours, is_overtime, notes, notification_sent, requested_by, approved_by,
                    is_active, created_at, updated_at, cobertura_id, folga_trabalhada, horas, shift_cobertura_id, alocacao_id)
                VALUES (CAST(:id AS uuid), CAST(:sh AS uuid), CAST(:p AS uuid), CAST(:c AS uuid), CAST(:s AS uuid),
                    :r, :det, 'confirmed', :d, :agora, :agora,
                    0, :oh, :folga, :nota, false, CAST(:u AS uuid), CAST(:u AS uuid),
                    true, :agora, :agora, CAST(:g AS uuid), :folga, :h, CAST(:esp AS uuid), CAST(:al AS uuid))
                """
            ),
            {
                "id": sid,
                "sh": ref["shift_id"],
                "p": post_id,
                "c": coberto_id,
                "s": cobertura_id,
                "r": reason,
                "det": (obs or "")[:500] or None,
                "d": d,
                "agora": agora,
                "oh": ref["horas"] if folga else 0,
                "folga": folga,
                "nota": nota,
                "u": user_id or None,
                "g": grupo,
                "h": ref["horas"],
                "esp": shift_esp,
                "al": alocacao_id,
            },
        )
        ids.append(sid)
    await db.commit()
    return {
        "cobertura_id": grupo,
        "dias": len(ids),
        "em_folga": sum(1 for _, _, f in dias if f),
        "horas": round(sum(r["horas"] for _, r, _ in dias), 2),
        "alocacao_id": alocacao_id,
        "ids": ids,
    }
