"""Espelho de Ponto — MOTOR de cálculo mensal (Portaria 671/2021).

Calcula o espelho de ponto LEGAL de um funcionário a partir do dado REAL
(`gp_clock_punches`) e grava/atualiza a linha em `time_sheets`. É a fonte que
o leitor/painel/PDF (`espelho_ponto_service.py` + `espelho_ponto_pdf.py`) e a
homologação do Meu Espaço consomem.

Princípios (ver skill folha-cct + auditoria defensiva A1):
- NUNCA fabrica batida. Dia sem par / par ímpar / batida manual → ANOMALIA
  registrada em `pending_issues` (JSON) + `has_pending_issues=true`, jamais uma
  batida inventada.
- Somente LEITURA de gp_clock_punches / employees / shifts (escala) / feriados /
  justificativas. ESCRITA apenas em `time_sheets`.
- Dinheiro é da FOLHA (calculo_service). Aqui o produto são as HORAS legais; os
  campos monetários de time_sheets ficam como REFERÊNCIA (folha oficial prevalece).

FÓRMULAS (base CCT SINDECOMPRESTS AM000613/2025 — agentes de portaria):

1. Pareamento cronológico entrada→saída (o turno 12x36 CRUZA a meia-noite, então
   NÃO se agrupa por dia-calendário). Um TURNO = sequência de pares cujo intervalo
   entre um par e o próximo é < 180 min (intrajornada); intervalos ≥ 180 min
   separam turnos. O turno é atribuído à DATA da 1ª entrada.
   BORDA DO MÊS: as batidas são lidas com margem de ±24h além do mês (SPILL_MARGIN_H)
   para que o turno que entra 30/x 22:00 e sai 01/(x+1) feche corretamente. Depois
   do pareamento, mantém-se no espelho SÓ os turnos cuja 1ª entrada cai no mês-alvo
   (o turno pertence ao mês em que COMEÇA); o que vira do/para o mês vizinho conta
   no espelho do mês vizinho — sem par_incompleto/saida_sem_entrada fantasma de borda.

2. Horas trabalhadas = Σ (saída − entrada) de cada par válido (0 < dur < 24h).
   Intervalo (break) = Σ dos gaps intra-turno.

3. Jornada esperada por turno (líquida, já sem intervalo):
   - 12x36: 660 min/turno (12h − 1h de intervalo).            [divisor mês = 180h]
   - 44h  : seg–sex 480 min (8h), sáb 240 min (4h), dom 0.    [divisor mês = 220h]
   Esperado do mês = Σ do esperado dos turnos trabalhados (+ dias de escala sem
   batida, quando há oráculo de escala publicado).

4. Adicional noturno — janela 22:00–05:00. Hora noturna REDUZIDA = 52'30" (52,5 min):
   min_noturnos_reais no intervalo → horas fictas = reais × (60 / 52,5).
   `night_hours_minutes` guarda os minutos noturnos REDUZIDOS (a qtd legal de horas
   noturnas, base do adicional de 20%). O ganho da hora ficta (redução) e o real
   ficam detalhados no daily_summary.

5. Horas extras = max(0, trabalhado_no_turno − esperado_do_turno). Classificação:
   - 12x36: 100% só em feriado; caso contrário 50%.
   - 44h  : 100% em domingo/feriado/dia de descanso (esperado=0); caso contrário 50%.

6. Atraso / saída antecipada — só apurável contra HORÁRIO PLANEJADO (oráculo de
   escala `shifts`). Sem escala publicada no mês (ex.: jun/2026), NÃO se apura
   (fica 0 + nota honesta), jamais se estima.

7. DSR — 12x36 já contempla no piso (dsr_entitled=True). Faltas injustificadas
   fazem perder o DSR da semana (só quando há oráculo de escala p/ apurar falta).

ANOMALIAS (pending_issues[].type):
- "par_incompleto"  : entrada sem saída (ou saída ausente no fim do turno/mês).
- "saida_sem_entrada": saída sem entrada aberta.
- "par_invalido"    : par com duração <=0 ou >=24h.
- "batida_manual"   : device_type manual/ajuste → exige conferência do DP.
- "dia_sem_batida"  : dia de escala publicada sem nenhuma batida (só com oráculo).
Cada anomalia carrega `justified` (True se coberta por justificativa aprovada /
férias / afastamento) — anomalia com justificativa NÃO bloqueia o fechamento.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ── Constantes de cálculo (folha-cct) ──────────────────────────────────────
NIGHT_START = time(22, 0)
NIGHT_END = time(5, 0)
REDUCED_NIGHT_MIN = 52.5  # hora noturna reduzida = 52'30"
NIGHT_FACTOR = 60.0 / REDUCED_NIGHT_MIN  # ≈ 1.142857

INTRA_SHIFT_GAP_MAX = 180  # min: gap < 180 = intervalo intrajornada (mesmo turno)
MAX_PAIR_MIN = 24 * 60     # par com dur >= 24h é inválido
# margem lida além das bordas do mês p/ fechar turno que cruza a virada do mês
SPILL_MARGIN_H = 24

EXPECTED_12X36_MIN = 660           # 12h - 1h intervalo
EXPECTED_44H = {0: 480, 1: 480, 2: 480, 3: 480, 4: 480, 5: 240, 6: 0}  # seg..dom
ESPERADO_MES_HORAS = {"12x36": 180.0, "44h": 220.0}
DIVISOR = {"12x36": 180.0, "44h": 220.0}

MANUAL_DEVICE_TYPES = {"manual", "ajuste", "ajuste_dp", "web_manual", "portal", "portal_manual", "corrigido"}

STATUS_CALCULADO = "calculado"
STATUS_FECHADO = "fechado"
# status que o leitor (espelho_ponto_service) considera "mês fechado"
STATUS_FECHADO_SET = {"fechado", "aprovado", "revisado", "enviado_folha"}


def _hhmm(dt: datetime | None) -> str:
    return dt.strftime("%H:%M") if dt else "—"


def _mes_bounds(mes: int, ano: int) -> tuple[date, date]:
    """(1º dia do mês, 1º dia do mês seguinte)."""
    ini = date(ano, mes, 1)
    fim = date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1)
    return ini, fim


def _minutos_noturnos(inicio: datetime, fim: datetime) -> float:
    """Minutos de [inicio, fim] dentro da janela noturna 22:00–05:00 (cruza meia-noite)."""
    total = 0.0
    d = inicio.date() - timedelta(days=1)
    end_date = fim.date()
    while d <= end_date:
        win_start = datetime.combine(d, NIGHT_START)
        win_end = datetime.combine(d + timedelta(days=1), NIGHT_END)
        ov_start = max(inicio, win_start)
        ov_end = min(fim, win_end)
        if ov_start < ov_end:
            total += (ov_end - ov_start).total_seconds() / 60.0
        d += timedelta(days=1)
    return total


def _normaliza_escala(escala: str | None) -> str:
    e = (escala or "").strip().lower()
    if "12" in e and "36" in e:
        return "12x36"
    if "44" in e:
        return "44h"
    return "12x36"  # default portaria


# ── Leitura de dado real (READ-ONLY) ───────────────────────────────────────
def _carregar_funcionario(db: Session, employee_id: str) -> dict[str, Any] | None:
    row = db.execute(
        text(
            "SELECT CAST(id AS TEXT) AS id, nome, matricula, cpf, pis, cargo, "
            "       posto_atual_nome, departamento, escala_padrao, salario_base "
            "FROM employees WHERE CAST(id AS TEXT) = :e"
        ),
        {"e": str(employee_id)},
    ).mappings().first()
    return dict(row) if row else None


def _carregar_batidas(db: Session, employee_id: str, mes: int, ano: int) -> list[dict[str, Any]]:
    """Batidas do mês COM margem de ±SPILL_MARGIN_H nas bordas, para fechar o turno
    que cruza a virada do mês. O recorte final (turno pertence ao mês em que começa)
    é feito em calcular_espelho após o pareamento."""
    ini, fim = _mes_bounds(mes, ano)
    lo = datetime.combine(ini, time(0, 0)) - timedelta(hours=SPILL_MARGIN_H)
    hi = datetime.combine(fim, time(0, 0)) + timedelta(hours=SPILL_MARGIN_H)
    rows = db.execute(
        text(
            "SELECT punch_id, punch_type, (punch_timestamp) AS punch_timestamp, status, device_type, "
            "       COALESCE(justification_id,'') AS justification_id "
            "FROM gp_clock_punches "
            "WHERE CAST(employee_id AS TEXT) = :e "
            "  AND (punch_timestamp) >= :lo AND (punch_timestamp) < :hi "
            # Desempate DETERMINÍSTICO p/ batidas no MESMO timestamp: SAÍDA antes de
            # ENTRADA (fecha o turno aberto antes de abrir o próximo — troca de turno)
            # e punch_id como desempate final. Sem isso, o pareamento (e o espelho
            # legal) dependeria da ordem física de linha do banco. NÃO fabrica nada:
            # só fixa a ordem de leitura de batidas que já existem.
            "ORDER BY punch_timestamp, "
            "  CASE WHEN lower(COALESCE(punch_type,'')) LIKE 'sa%' THEN 0 ELSE 1 END, "
            "  punch_id"
        ),
        {"e": str(employee_id), "lo": lo, "hi": hi},
    ).mappings().all()
    return [dict(r) for r in rows]


def _carregar_feriados(db: Session, mes: int, ano: int) -> set[date]:
    try:
        rows = db.execute(
            text(
                "SELECT data_feriado FROM cct_feriados "
                "WHERE EXTRACT(MONTH FROM data_feriado)=:m AND EXTRACT(YEAR FROM data_feriado)=:y "
                "AND COALESCE(is_active,true)=true"
            ),
            {"m": int(mes), "y": int(ano)},
        ).fetchall()
        return {r[0] for r in rows if r[0]}
    except Exception as exc:  # noqa: BLE001
        logger.debug("feriados indisponíveis: %s", exc)
        return set()


def _carregar_escala_oraculo(db: Session, employee_id: str, mes: int, ano: int) -> dict[date, dict]:
    """Dias de escala PUBLICADA (tabela shifts) do funcionário no mês, se existirem.

    Retorna {shift_date: {planned_start, planned_end, planned_break, is_off_day}}.
    Ausente (ex.: jun/2026) → dict vazio; o motor não estima faltas/atrasos.
    """
    try:
        rows = db.execute(
            text(
                "SELECT shift_date, planned_start_time, planned_end_time, "
                "       COALESCE(planned_break_minutes,0) AS brk, COALESCE(is_off_day,false) AS off "
                "FROM shifts WHERE CAST(employee_id AS TEXT)=:e "
                "AND shift_date >= :ini AND shift_date < :fim"
            ),
            {"e": str(employee_id), "ini": date(ano, mes, 1),
             "fim": (date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1))},
        ).mappings().all()
        return {
            r["shift_date"]: {
                "planned_start": r["planned_start_time"],
                "planned_end": r["planned_end_time"],
                "planned_break": r["brk"],
                "is_off_day": r["off"],
            }
            for r in rows
        }
    except Exception as exc:  # noqa: BLE001
        logger.debug("escala (shifts) indisponível: %s", exc)
        return {}


def _dia_coberto_por_abono(db: Session, employee_id: str, dia: date) -> str | None:
    """Retorna motivo se o dia está coberto por justificativa aprovada / férias /
    afastamento; senão None. Usado para marcar anomalia como justificada."""
    # 1. Justificativa de ponto aprovada nesse dia
    try:
        r = db.execute(
            text(
                "SELECT j.reason FROM gp_justifications j "
                "LEFT JOIN gp_clock_punches p ON p.punch_id = j.punch_id "
                "WHERE CAST(j.employee_id AS TEXT)=:e AND lower(j.status) IN ('aprovada','approved') "
                # casa pela data do FATO (a batida que a justificativa cobre) OU, na falta de
                # punch_id, pela data de lançamento — assim atestado lançado dias DEPOIS da
                # falta ainda cobre o dia certo (antes só `created_at::date` → virava falta)
                "AND ((punch_timestamp)::date = :d OR j.created_at::date = :d) LIMIT 1"
            ),
            {"e": str(employee_id), "d": dia},
        ).first()
        if r:
            return f"justificativa aprovada: {r[0]}"
    except Exception:  # noqa: BLE001
        pass
    # 2. Férias aprovadas cobrindo o dia
    try:
        r = db.execute(
            text(
                "SELECT 1 FROM hr_vacation_requests "
                "WHERE CAST(employee_id AS TEXT)=:e AND lower(COALESCE(status,'')) IN "
                "('aprovada','approved','hr_approved','gozando','concluida') "
                "AND :d BETWEEN start_date AND end_date LIMIT 1"
            ),
            {"e": str(employee_id), "d": dia},
        ).first()
        if r:
            return "férias"
    except Exception:  # noqa: BLE001
        pass
    # 3. Afastamento SST cobrindo o dia
    try:
        r = db.execute(
            text(
                "SELECT tipo FROM sst_afastamentos "
                "WHERE CAST(employee_id AS TEXT)=:e "
                "AND :d >= data_inicio AND :d <= COALESCE(data_retorno, data_fim_prevista, :d) LIMIT 1"
            ),
            {"e": str(employee_id), "d": dia},
        ).first()
        if r:
            return f"afastamento ({r[0]})"
    except Exception:  # noqa: BLE001
        pass
    return None


# ── Núcleo: pareamento + turnos ─────────────────────────────────────────────
def _parear(batidas: list[dict]) -> tuple[list[dict], list[dict]]:
    """Pareia entrada→saída cronologicamente. Retorna (pares, anomalias_de_par).

    pares: [{entrada, saida, dur_min, entrada_manual, saida_manual}]
    anomalias: [{type, date, description, punch_id}]
    """
    pares: list[dict] = []
    anomalias: list[dict] = []
    aberta: dict | None = None  # batida de entrada em aberto

    def _is_manual(b: dict) -> bool:
        dev = (b.get("device_type") or "").strip().lower()
        return dev in MANUAL_DEVICE_TYPES or bool(b.get("justification_id"))

    for b in batidas:
        tipo = (b.get("punch_type") or "").strip().lower()
        ts = b.get("punch_timestamp")
        abre = tipo.startswith("entrada") or tipo.startswith("retorno")
        fecha = tipo.startswith("saida") or tipo.startswith("saída")
        if abre:
            if aberta is not None:
                # entrada anterior nunca foi fechada
                anomalias.append({
                    "type": "par_incompleto",
                    "date": aberta["ts"].date().isoformat(),
                    "description": (
                        f"Entrada às {_hhmm(aberta['ts'])} sem saída correspondente "
                        f"(próxima batida é outra entrada às {_hhmm(ts)})."
                    ),
                    "punch_id": aberta.get("punch_id"),
                    "severity": "high",
                })
            aberta = {"ts": ts, "punch_id": b.get("punch_id"), "manual": _is_manual(b)}
        elif fecha:
            if aberta is None:
                anomalias.append({
                    "type": "saida_sem_entrada",
                    "date": ts.date().isoformat(),
                    "description": f"Saída às {_hhmm(ts)} sem entrada aberta correspondente.",
                    "punch_id": b.get("punch_id"),
                    "severity": "high",
                })
                continue
            dur = (ts - aberta["ts"]).total_seconds() / 60.0
            if dur <= 0 or dur >= MAX_PAIR_MIN:
                anomalias.append({
                    "type": "par_invalido",
                    "date": aberta["ts"].date().isoformat(),
                    "description": (
                        f"Par entrada {_hhmm(aberta['ts'])} → saída {_hhmm(ts)} com duração "
                        f"inválida ({dur/60:.1f}h)."
                    ),
                    "punch_id": aberta.get("punch_id"),
                    "severity": "high",
                })
            else:
                pares.append({
                    "entrada": aberta["ts"],
                    "saida": ts,
                    "dur_min": dur,
                    "entrada_manual": aberta["manual"],
                    "saida_manual": _is_manual(b),
                })
            aberta = None

    if aberta is not None:
        anomalias.append({
            "type": "par_incompleto",
            "date": aberta["ts"].date().isoformat(),
            "description": f"Entrada às {_hhmm(aberta['ts'])} sem saída (saída ausente no período).",
            "punch_id": aberta.get("punch_id"),
            "severity": "high",
        })

    return pares, anomalias


def _agrupar_turnos(pares: list[dict]) -> list[dict]:
    """Agrupa pares em TURNOS (gap intra-turno < 180 min = intervalo). Atribui à
    data da 1ª entrada. Retorna [{date, entrada, saida, pares, worked_min, break_min}]."""
    turnos: list[dict] = []
    atual: list[dict] = []

    def _fecha(grp: list[dict]) -> dict:
        worked = sum(p["dur_min"] for p in grp)
        break_min = 0.0
        for i in range(1, len(grp)):
            break_min += (grp[i]["entrada"] - grp[i - 1]["saida"]).total_seconds() / 60.0
        return {
            "date": grp[0]["entrada"].date(),
            "entrada": grp[0]["entrada"],
            "saida": grp[-1]["saida"],
            "pares": grp,
            "worked_min": worked,
            "break_min": break_min,
        }

    for p in pares:
        if not atual:
            atual = [p]
            continue
        gap = (p["entrada"] - atual[-1]["saida"]).total_seconds() / 60.0
        if 0 <= gap < INTRA_SHIFT_GAP_MAX:
            atual.append(p)  # mesmo turno, gap = intervalo
        else:
            turnos.append(_fecha(atual))
            atual = [p]
    if atual:
        turnos.append(_fecha(atual))
    return turnos


def _esperado_turno(escala: str, dia: date) -> int:
    if escala == "12x36":
        return EXPECTED_12X36_MIN
    return EXPECTED_44H.get(dia.weekday(), 0)


# ── Motor principal ─────────────────────────────────────────────────────────
def calcular_espelho(
    db: Session,
    employee_id: str,
    mes: int,
    ano: int,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Calcula o espelho do mês e grava/atualiza `time_sheets` (status='calculado').

    Retorna um resumo dict com totais + anomalias. NÃO fecha o mês (isso é do
    endpoint fechar-mes). Se o mês já estiver FECHADO e force=False, não recalcula
    por cima (protege o registro legal) — retorna o existente.
    """
    from modules.hr.time_tracking.models.time_sheet import TimeSheet

    emp = _carregar_funcionario(db, employee_id)
    if emp is None:
        raise ValueError("Colaborador não encontrado")

    escala = _normaliza_escala(emp.get("escala_padrao"))

    existing = (
        db.query(TimeSheet)
        .filter(
            TimeSheet.employee_id == str(employee_id),
            TimeSheet.reference_month == int(mes),
            TimeSheet.reference_year == int(ano),
            TimeSheet.is_deleted == False,  # noqa: E712
        )
        .first()
    )
    # Protege QUALQUER espelho já fechado / enviado à folha / HOMOLOGADO (assinado):
    # nunca sobrescreve em silêncio — o hash do PDF assinado deixaria de corresponder
    # aos dados. NEM com force: recálculo de espelho protegido exige reabertura
    # explícita (reopen_time_sheet), que invalida a homologação e a assinatura. O
    # recálculo em massa (force=true) corretamente PULA os meses já fechados.
    protegido = existing is not None and (
        (existing.status or "") in STATUS_FECHADO_SET
        or existing.closed_at is not None
        or bool(getattr(existing, "approved_by_employee", False))
    )
    if protegido:
        return _resumo_do_timesheet(existing, escala, ja_fechado=True)

    batidas = _carregar_batidas(db, employee_id, mes, ano)
    feriados = _carregar_feriados(db, mes, ano)
    escala_oraculo = _carregar_escala_oraculo(db, employee_id, mes, ano)

    pares, anomalias = _parear(batidas)
    turnos = _agrupar_turnos(pares)

    # ── Recorte do mês-alvo (pareamento cruza a borda; o espelho não) ──────────
    # O turno pertence ao mês em que COMEÇA (data da 1ª entrada). Turnos/anomalias
    # das margens de spill (mês vizinho) são descartados aqui — eles contam no
    # espelho do mês vizinho, não geram fantasma de borda neste.
    mes_ini, mes_fim = _mes_bounds(mes, ano)

    def _no_mes(d: date) -> bool:
        return mes_ini <= d < mes_fim

    turnos = [t for t in turnos if _no_mes(t["date"])]

    def _anom_no_mes(a: dict) -> bool:
        try:
            return _no_mes(date.fromisoformat(a["date"]))
        except Exception:  # noqa: BLE001
            return True  # sem data parseável: mantém (conservador)

    anomalias = [a for a in anomalias if _anom_no_mes(a)]

    # batidas efetivamente REGISTRADAS no mês (p/ contadores; o pareamento usou a
    # janela ampliada, mas os contadores refletem o calendário do mês)
    batidas_mes = [b for b in batidas if _no_mes(b["punch_timestamp"].date())]

    # Agregação
    worked_total = 0.0
    expected_total = 0.0
    night_real_total = 0.0
    night_reduced_total = 0.0
    break_total = 0.0
    ot50 = 0.0
    ot100 = 0.0
    late_total = 0.0
    late_count = 0
    early_total = 0.0
    daily: list[dict] = []

    tem_escala = len(escala_oraculo) > 0

    for t in turnos:
        dia = t["date"]
        worked = t["worked_min"]
        brk = t["break_min"]
        esperado = _esperado_turno(escala, dia)
        is_holiday = dia in feriados
        is_sunday = dia.weekday() == 6

        night_real = sum(_minutos_noturnos(p["entrada"], p["saida"]) for p in t["pares"])
        night_reduced = night_real * NIGHT_FACTOR

        overtime = max(0.0, worked - esperado)
        if escala == "12x36":
            is_100 = is_holiday
        else:
            is_100 = is_holiday or is_sunday or esperado == 0
        if is_100:
            ot100 += overtime
        else:
            ot50 += overtime

        # Atraso / saída antecipada — só com escala publicada
        late = early = 0.0
        ps = None
        if tem_escala and dia in escala_oraculo and not escala_oraculo[dia].get("is_off_day"):
            planned = escala_oraculo[dia]
            if planned.get("planned_start"):
                ps = datetime.combine(dia, planned["planned_start"])
                delta = (t["entrada"] - ps).total_seconds() / 60.0
                if delta > 5:  # tolerância 5 min
                    late = delta
                    late_total += delta
                    late_count += 1
            if planned.get("planned_end"):
                pe = datetime.combine(dia, planned["planned_end"])
                if ps is not None and pe < ps:  # vira o dia (só compara se houver início)
                    pe += timedelta(days=1)
                delta = (pe - t["saida"]).total_seconds() / 60.0
                if delta > 5:
                    early = delta
                    early_total += delta

        worked_total += worked
        expected_total += esperado
        night_real_total += night_real
        night_reduced_total += night_reduced
        break_total += brk

        manual = any(p["entrada_manual"] or p["saida_manual"] for p in t["pares"])
        if manual:
            anomalias.append({
                "type": "batida_manual",
                "date": dia.isoformat(),
                "description": f"Turno de {_hhmm(t['entrada'])}–{_hhmm(t['saida'])} contém batida manual/ajuste — conferir.",
                "severity": "medium",
            })

        notas = []
        if is_holiday:
            notas.append("Feriado")
        if manual:
            notas.append("Batida manual")
        if overtime > 0:
            notas.append(f"Extra {'100%' if is_100 else '50%'} {int(overtime)}min")

        daily.append({
            "date": dia.isoformat(),
            "entrada": _hhmm(t["entrada"]),
            "saida": _hhmm(t["saida"]),
            "intervalo": f"{int(brk)//60:02d}:{int(brk)%60:02d}" if brk > 0 else "",
            "worked": int(round(worked)),
            "expected": int(esperado),
            "overtime": int(round(overtime)),
            "overtime_type": "100" if is_100 else "50",
            "night_real": int(round(night_real)),
            "night_ficta": int(round(night_reduced)),
            "late": int(round(late)),
            "early": int(round(early)),
            "is_holiday": is_holiday,
            "is_absent": False,
            "notes": "; ".join(notas) if notas else None,
        })

    # Dias de escala publicada sem batida → anomalia (só com oráculo)
    absent_days = 0
    unjustified_absent = 0
    if tem_escala:
        dias_com_turno = {t["date"] for t in turnos}
        for dia, info in sorted(escala_oraculo.items()):
            if info.get("is_off_day"):
                continue
            if dia in dias_com_turno:
                continue
            motivo = _dia_coberto_por_abono(db, employee_id, dia)
            anomalias.append({
                "type": "dia_sem_batida",
                "date": dia.isoformat(),
                "description": (
                    f"Dia de escala sem nenhuma batida de ponto."
                    + (f" Coberto por {motivo}." if motivo else " Sem justificativa.")
                ),
                "severity": "medium" if motivo else "high",
                "justified": bool(motivo),
                "justification": motivo,
            })
            absent_days += 1
            if not motivo:
                unjustified_absent += 1
                # dia de escala sem batida e SEM cobertura entra no ESPERADO: o débito
                # de jornada tem que aparecer no saldo (coerente com o docstring; dia
                # justificado por férias/atestado NÃO é débito, por isso fica de fora)
                expected_total += _esperado_turno(escala, dia)

    # Marca justificativa das anomalias de dia (par_incompleto etc.) por data
    for a in anomalias:
        if "justified" in a:
            continue
        try:
            dia = date.fromisoformat(a["date"])
        except Exception:  # noqa: BLE001
            a["justified"] = False
            continue
        motivo = _dia_coberto_por_abono(db, employee_id, dia)
        a["justified"] = bool(motivo)
        if motivo:
            a["justification"] = motivo

    # DSR
    dsr_entitled = True
    dsr_lost_days = 0
    if escala != "12x36" and unjustified_absent > 0:
        dsr_entitled = False
        dsr_lost_days = unjustified_absent  # 1 DSR por falta injustificada (aprox. semanal)

    anomalias_abertas = [a for a in anomalias if not a.get("justified")]
    has_pending = len(anomalias_abertas) > 0
    resolvidas = len(anomalias) - len(anomalias_abertas)

    balance = worked_total - expected_total
    night_reduced_min = int(round(night_reduced_total))

    # Notas do período (limitações honestas)
    obs = []
    if not tem_escala:
        obs.append(
            "Escala não publicada para o mês (tabela shifts vazia): faltas, atrasos e "
            "saídas antecipadas NÃO foram apurados pelo motor — apenas horas efetivas e "
            "anomalias de pareamento. Não há estimativa/fabricação."
        )
    if not batidas_mes:
        obs.append("Nenhuma batida no período.")

    hourly_rate = None
    try:
        if emp.get("salario_base"):
            hourly_rate = float(emp["salario_base"]) / DIVISOR.get(escala, 220.0)
    except Exception:  # noqa: BLE001
        hourly_rate = None

    metadata = {
        "motor_versao": "1.1",
        "escala": escala,
        "esperado_mes_horas": ESPERADO_MES_HORAS.get(escala),
        "night_real_minutes": int(round(night_real_total)),
        "night_reduced_minutes": night_reduced_min,
        "night_factor": round(NIGHT_FACTOR, 6),
        "reduced_night_min_rule": REDUCED_NIGHT_MIN,
        "tem_escala_publicada": tem_escala,
        "total_batidas": len(batidas_mes),
        "total_turnos": len(turnos),
        "spill_margin_horas": SPILL_MARGIN_H,
        "observacoes": obs,
        "dinheiro_fonte": "folha oficial (calculo_service) prevalece; valores aqui são referência",
    }

    from datetime import datetime as _dt

    if existing is None:
        ts = TimeSheet(
            reference_month=int(mes),
            reference_year=int(ano),
            employee_id=str(employee_id),
            employee_name=emp.get("nome") or "—",
        )
        db.add(ts)
    else:
        ts = existing

    ts.employee_name = emp.get("nome") or ts.employee_name or "—"
    ts.employee_registration = emp.get("matricula")
    ts.employee_cpf = emp.get("cpf")
    ts.employee_pis = emp.get("pis")
    ts.position_name = emp.get("cargo")
    ts.department_name = emp.get("departamento")
    ts.condominium_name = emp.get("posto_atual_nome")
    ts.work_schedule_name = escala
    ts.weekly_hours_expected = int(ESPERADO_MES_HORAS.get(escala, 220.0) * 60)

    ts.status = STATUS_CALCULADO
    ts.hours_worked_minutes = int(round(worked_total))
    ts.hours_expected_minutes = int(round(expected_total))
    ts.hours_balance_minutes = int(round(balance))
    ts.overtime_50_minutes = int(round(ot50))
    ts.overtime_100_minutes = int(round(ot100))
    ts.overtime_total_minutes = int(round(ot50 + ot100))
    ts.night_hours_minutes = night_reduced_min
    ts.late_minutes = int(round(late_total))
    ts.late_count = late_count
    ts.early_departure_minutes = int(round(early_total))
    ts.break_actual_minutes = int(round(break_total))
    ts.work_days_worked = len(turnos)
    ts.absent_days = absent_days
    ts.unjustified_absent_days = unjustified_absent
    ts.dsr_entitled = dsr_entitled
    ts.dsr_lost_days = dsr_lost_days
    ts.total_entries = len(batidas_mes)
    ts.anomaly_count = len(anomalias)
    ts.anomaly_resolved_count = resolvidas
    ts.manual_entries_count = sum(
        1 for b in batidas_mes
        if (b.get("device_type") or "").lower() in MANUAL_DEVICE_TYPES or b.get("justification_id")
    )
    ts.has_pending_issues = has_pending
    ts.pending_issues = anomalias
    ts.daily_summary = daily
    if hourly_rate is not None:
        from decimal import Decimal
        ts.hourly_rate = Decimal(str(round(hourly_rate, 2)))
    ts.extra_metadata = metadata
    ts.notes = " | ".join(obs) if obs else None
    ts.last_calculated_at = _dt.utcnow()

    db.flush()

    return {
        "employee_id": str(employee_id),
        "employee_name": ts.employee_name,
        "escala": escala,
        "mes": int(mes),
        "ano": int(ano),
        "status": ts.status,
        "hours_worked_minutes": ts.hours_worked_minutes,
        "hours_expected_minutes": ts.hours_expected_minutes,
        "hours_balance_minutes": ts.hours_balance_minutes,
        "overtime_50_minutes": ts.overtime_50_minutes,
        "overtime_100_minutes": ts.overtime_100_minutes,
        "night_hours_minutes": ts.night_hours_minutes,
        "night_real_minutes": metadata["night_real_minutes"],
        "late_minutes": ts.late_minutes,
        "break_actual_minutes": ts.break_actual_minutes,
        "work_days_worked": ts.work_days_worked,
        "absent_days": ts.absent_days,
        "unjustified_absent_days": ts.unjustified_absent_days,
        "total_batidas": len(batidas_mes),
        "total_turnos": len(turnos),
        "anomaly_count": ts.anomaly_count,
        "anomaly_open_count": len(anomalias_abertas),
        "has_pending_issues": ts.has_pending_issues,
        "anomalias": anomalias,
        "observacoes": obs,
        "time_sheet_id": str(ts.id),
    }


def _resumo_do_timesheet(ts, escala: str, *, ja_fechado: bool = False) -> dict[str, Any]:
    anomalias = ts.pending_issues or []
    abertas = [a for a in anomalias if not (isinstance(a, dict) and a.get("justified"))]
    return {
        "employee_id": str(ts.employee_id),
        "employee_name": ts.employee_name,
        "escala": escala,
        "mes": int(ts.reference_month),
        "ano": int(ts.reference_year),
        "status": ts.status,
        "hours_worked_minutes": ts.hours_worked_minutes,
        "hours_expected_minutes": ts.hours_expected_minutes,
        "hours_balance_minutes": ts.hours_balance_minutes,
        "overtime_50_minutes": ts.overtime_50_minutes,
        "overtime_100_minutes": ts.overtime_100_minutes,
        "night_hours_minutes": ts.night_hours_minutes,
        "late_minutes": ts.late_minutes,
        "work_days_worked": ts.work_days_worked,
        "absent_days": ts.absent_days,
        "anomaly_count": ts.anomaly_count,
        "anomaly_open_count": len(abertas),
        "has_pending_issues": ts.has_pending_issues,
        "anomalias": anomalias,
        "ja_fechado": ja_fechado,
        "time_sheet_id": str(ts.id),
    }


# ── Fechamento e status ─────────────────────────────────────────────────────
def _employees_com_batida(db: Session, mes: int, ano: int) -> list[str]:
    rows = db.execute(
        text(
            "SELECT DISTINCT CAST(employee_id AS TEXT) AS e FROM gp_clock_punches "
            "WHERE EXTRACT(MONTH FROM (punch_timestamp))=:m AND EXTRACT(YEAR FROM (punch_timestamp))=:y "
            # Homologação NÃO entra no fechamento/folha de produção (isolamento de teste)
            "  AND employee_id NOT IN (SELECT id FROM employees WHERE coalesce(is_homologacao, false) = true)"
        ),
        {"m": int(mes), "y": int(ano)},
    ).fetchall()
    return [r[0] for r in rows]


def fechar_mes(
    db: Session,
    mes: int,
    ano: int,
    *,
    employee_id: str | None = None,
    fechar: bool = True,
    closed_by: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Calcula o mês (um ou todos) e, para os espelhos SEM anomalia aberta, aplica o
    fechamento DEFINITIVO (status='fechado', closed_at, closed_by). Espelhos com
    anomalia aberta permanecem 'calculado' e voltam na lista `bloqueados` — nunca
    são fechados automaticamente."""
    from modules.hr.time_tracking.models.time_sheet import TimeSheet

    alvos = [employee_id] if employee_id else _employees_com_batida(db, mes, ano)

    calculados: list[dict] = []
    fechados: list[dict] = []
    bloqueados: list[dict] = []
    erros: list[dict] = []

    for eid in alvos:
        try:
            resumo = calcular_espelho(db, eid, mes, ano, force=force)
        except Exception as exc:  # noqa: BLE001
            erros.append({"employee_id": str(eid), "erro": str(exc)})
            continue
        calculados.append(resumo)
        if resumo.get("has_pending_issues"):
            bloqueados.append({
                "employee_id": resumo["employee_id"],
                "employee_name": resumo.get("employee_name"),
                "anomaly_open_count": resumo.get("anomaly_open_count"),
                "anomalias": [a for a in resumo.get("anomalias", []) if not a.get("justified")],
            })
            continue
        if fechar and not resumo.get("ja_fechado"):
            ts = (
                db.query(TimeSheet)
                .filter(
                    TimeSheet.employee_id == str(resumo["employee_id"]),
                    TimeSheet.reference_month == int(mes),
                    TimeSheet.reference_year == int(ano),
                    TimeSheet.is_deleted == False,  # noqa: E712
                )
                .first()
            )
            if ts is not None:
                ts.status = STATUS_FECHADO
                ts.closed_at = datetime.utcnow()
                ts.closed_by_id = (closed_by or "")[:50] or None
                ts.closed_by_name = closed_by
                db.flush()
                fechados.append({
                    "employee_id": resumo["employee_id"],
                    "employee_name": resumo.get("employee_name"),
                })

    return {
        "mes": int(mes),
        "ano": int(ano),
        "competencia": f"{int(mes):02d}/{ano}",
        "escopo": "individual" if employee_id else "todos",
        "resumo": {
            "total_processados": len(calculados),
            "com_anomalia": len(bloqueados),
            "fechados": len(fechados),
            "erros": len(erros),
        },
        "fechados": fechados,
        "bloqueados": bloqueados,
        "erros": erros,
        "pode_fechar_todos": len(bloqueados) == 0 and len(calculados) > 0,
        "aviso": (
            "Existem espelhos com anomalia ABERTA — corrija/justifique (justificativa "
            "de ponto, férias ou afastamento) antes do fechamento definitivo."
            if bloqueados else "Todos os espelhos processados estão sem anomalia aberta."
        ),
    }


def fechamento_status(
    db: Session, mes: int, ano: int, *, employee_id: str | None = None
) -> dict[str, Any]:
    """Status por funcionário do mês (lê apenas time_sheets já calculados):
    calculado? anomalias? fechado? homologado (approved_by_employee)?"""
    params: dict[str, Any] = {"m": int(mes), "y": int(ano)}
    filtro_emp = ""
    if employee_id:
        filtro_emp = " AND CAST(employee_id AS TEXT) = :e"
        params["e"] = str(employee_id)

    rows = db.execute(
        text(
            """
            SELECT CAST(id AS TEXT) AS id, CAST(employee_id AS TEXT) AS employee_id,
                   employee_name, position_name, condominium_name, work_schedule_name,
                   status, hours_worked_minutes, hours_expected_minutes, hours_balance_minutes,
                   overtime_total_minutes, night_hours_minutes, absent_days,
                   anomaly_count, anomaly_resolved_count, has_pending_issues,
                   approved_by_employee, employee_approved_at, closed_at,
                   last_calculated_at
            FROM time_sheets
            WHERE reference_month = :m AND reference_year = :y
              AND COALESCE(is_deleted, false) = false
            """ + filtro_emp + " ORDER BY employee_name"
        ),
        params,
    ).mappings().all()

    itens: list[dict] = []
    tot = {"total": 0, "calculados": 0, "com_anomalia": 0, "fechados": 0, "homologados": 0}
    for r in rows:
        abertas = max(int(r.get("anomaly_count") or 0) - int(r.get("anomaly_resolved_count") or 0), 0)
        fechado = (r.get("status") or "") in STATUS_FECHADO_SET
        homologado = bool(r.get("approved_by_employee"))
        itens.append({
            "time_sheet_id": r["id"],
            "employee_id": r["employee_id"],
            "employee_name": r.get("employee_name") or "—",
            "position_name": r.get("position_name"),
            "condominium_name": r.get("condominium_name"),
            "escala": r.get("work_schedule_name"),
            "status": r.get("status"),
            "calculado": True,
            "hours_worked_minutes": r.get("hours_worked_minutes"),
            "hours_expected_minutes": r.get("hours_expected_minutes"),
            "hours_balance_minutes": r.get("hours_balance_minutes"),
            "overtime_total_minutes": r.get("overtime_total_minutes"),
            "night_hours_minutes": r.get("night_hours_minutes"),
            "absent_days": int(r.get("absent_days") or 0),
            "anomalias_abertas": abertas,
            "has_pending_issues": bool(r.get("has_pending_issues")),
            "fechado": fechado,
            "closed_at": r.get("closed_at").isoformat() if r.get("closed_at") else None,
            "homologado": homologado,
            "employee_approved_at": (
                r.get("employee_approved_at").isoformat() if r.get("employee_approved_at") else None
            ),
            "last_calculated_at": (
                r.get("last_calculated_at").isoformat() if r.get("last_calculated_at") else None
            ),
        })
        tot["total"] += 1
        tot["calculados"] += 1
        if abertas > 0:
            tot["com_anomalia"] += 1
        if fechado:
            tot["fechados"] += 1
        if homologado:
            tot["homologados"] += 1

    return {
        "mes": int(mes),
        "ano": int(ano),
        "competencia": f"{int(mes):02d}/{ano}",
        "resumo": tot,
        "pode_fechar": tot["com_anomalia"] == 0 and tot["total"] > 0,
        "funcionarios": itens,
    }
