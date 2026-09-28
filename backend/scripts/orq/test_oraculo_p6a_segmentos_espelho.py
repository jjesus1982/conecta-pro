#!/usr/bin/env python3
"""Oráculo P6a — o espelho de ponto mostra CADA par do plantão, e diz o que faltou marcar.

Por que existe: o motor do espelho (`espelho_service._parear` / `_agrupar_turnos`) já pareava
entrada→saída corretamente, inclusive no noturno que cruza a meia-noite, e **jogava os pares
fora** no `daily.append`. O `daily_summary` — que é a folha de ponto que o colaborador ASSINA,
vira PDF, entra no kit do GEDEON e vai à homologação — guardava uma linha por dia com a
PRIMEIRA entrada e a ÚLTIMA saída. Um plantão 19:00→02:00 + 03:00→07:17 saía como
"19:00 → 07:17": o intervalo de 1h simplesmente não existia no documento.

Medido em 28/09/2026 sobre 09/2026 (675 turnos, 55 pessoas): **375 dias (56%) têm 2+
segmentos** que a linha única escondia, e **44 dias têm batida órfã** que o motor descartava
do detalhe (`saida`: 20 · `retorno_almoco`: 22 · `entrada`: 11 · `saida_almoco`: 2). Nos 30
dias anteriores, 115 dias-pessoa (12%) tinham marcação de almoço ÍMPAR — 106 com uma só marca
e 9 com três. Uma estrutura que assume "1 ou 2 pares" produz lixo em 12% dos dias.

REGRAS afirmadas (regra, nunca fotografia — nenhum nome, id ou data aqui):

  R1  Todo dia do espelho traz `segmentos`, um por par do motor: `len(completos)` é igual a
      `len(t["pares"])`. Nenhum par é perdido nem duplicado no caminho.
  R2  A soma dos minutos dos segmentos completos reproduz as horas do dia (folga de 1 min por
      par, que é o arredondamento de cada par isolado). A linha única não pode esconder tempo.
  R3  Batida órfã (marca sem o seu par) aparece como segmento INCOMPLETO nomeando em `falta` a
      marca que não veio, com EXATAMENTE UMA ponta preenchida e `minutos == 0`. NUNCA se
      inventa a hora que falta.
  R4  Contabilidade fechada: toda batida órfã que o motor descartou está num segmento
      incompleto, ou cai num dia sem nenhum par válido (aí não há linha — e ela continua
      visível em `pending_issues`). Nenhuma órfã desaparece em silêncio.
  R5  Contrato de `daily_summary` intacto: as chaves que os CINCO consumidores leem continuam
      todas lá (`he_classificacao`, `folha/feriado_conferencia`, `espelho_ponto_pdf`,
      `report_service` ACJEF, tela do DP). `segmentos` é ACRÉSCIMO.
  R6  Quem consome TOLERA a ausência da chave: existe um SEGUNDO escritor de `daily_summary`
      (`hr/time_tracking/services/time_sheet_service._process_day`) que não grava `segmentos`.
      Dia sem a chave não pode derrubar a tela nem mover um byte do ACJEF (arquivo de governo,
      largura fixa).

CONTROLE (por que este oráculo não é cúmplice): as mesmas seis regras são rodadas contra o
comportamento ANTERIOR, reconstruído aqui (`_segmentos_da_linha_unica`: uma linha por dia com
a primeira entrada e a última saída, que é literalmente o que o `daily.append` gravava). Se o
controle passar, o oráculo está medindo o nada e sai VERMELHO por isso.

Roda sem escrever nada — fixtures são em memória, e a passada em dado real é só leitura:
    docker exec -i -e PYTHONPATH=/app conecta-pro-backend \\
        python3 /app/scripts/orq/test_oraculo_p6a_segmentos_espelho.py

Linha canônica: `TOTAL: <n> regra(s) de segmento violada(s)`. Exit 1 se houver.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta

# ── chaves que os consumidores de daily_summary leem (R5) ───────────────────
CONTRATO = (
    "date",
    "entrada",
    "saida",
    "intervalo",
    "worked",
    "expected",
    "overtime",
    "overtime_type",
    "night_real",
    "night_ficta",
    "late",
    "early",
    "is_holiday",
    "is_absent",
    "notes",
)

D0 = date(2026, 4, 6)  # data neutra qualquer; nenhuma regra depende dela


def _b(dia_off: int, hhmm: str, tipo: str, n: int = 0) -> dict:
    h, m = (int(x) for x in hhmm.split(":"))
    return {
        "punch_id": f"fix-{dia_off}-{hhmm}-{tipo}-{n}",
        "punch_type": tipo,
        "punch_timestamp": datetime.combine(D0 + timedelta(days=dia_off), datetime.min.time())
        + timedelta(hours=h, minutes=m),
        "status": "approved",
        "device_type": "mobile",
        "justification_id": "",
    }


#: (rótulo, batidas, nº de segmentos completos, faltas esperadas em ordem)
FIXTURES = (
    # o par único: um plantão sem intervalo marcado
    ("1 par", [_b(0, "08:00", "entrada"), _b(0, "17:00", "saida")], 1, ()),
    # o caso que a linha única destruía: intervalo DENTRO de plantão noturno
    (
        "2 pares · noturno cruzando meia-noite",
        [
            _b(0, "19:00", "entrada"),
            _b(1, "02:00", "saida"),
            _b(1, "03:00", "entrada"),
            _b(1, "07:17", "saida"),
        ],
        2,
        (),
    ),
    # 12% dos dias: intervalo ÍMPAR — saiu para o almoço e não marcou o retorno
    (
        "intervalo incompleto · falta retorno",
        [_b(0, "08:00", "entrada"), _b(0, "12:00", "saida_almoco"), _b(0, "17:00", "saida")],
        1,
        ("retorno_almoco",),
    ),
    # três marcas de almoço: marcou retorno duas vezes, faltou a saída do 2º
    (
        "intervalo incompleto · três marcas",
        [
            _b(0, "08:00", "entrada"),
            _b(0, "12:00", "saida_almoco"),
            _b(0, "13:00", "retorno_almoco"),
            _b(0, "13:02", "retorno_almoco"),
            _b(0, "17:00", "saida"),
        ],
        2,
        ("saida_almoco",),
    ),
    # abertura que nunca veio: a saída existe e não tem par
    (
        "saída sem abertura",
        [_b(0, "12:00", "saida"), _b(0, "13:00", "entrada"), _b(0, "17:00", "saida")],
        1,
        ("entrada",),
    ),
)


# ─────────────────────── o comportamento ANTERIOR (controle) ───────────────────────
def _segmentos_da_linha_unica(pares: list[dict], orfaos: list[dict]) -> list[dict]:
    """O que o `daily.append` gravava antes da P6a: UMA linha por dia — primeira entrada,
    última saída — e a batida órfã em lugar nenhum. É o controle: as regras têm de reprovar."""
    from modules.people_management.hr.services.espelho_service import _hhmm

    if not pares:
        return []
    return [
        {
            "entrada": _hhmm(pares[0]["entrada"]),
            "saida": _hhmm(pares[-1]["saida"]),
            "minutos": int(round(sum(p["dur_min"] for p in pares))),
            "entrada_manual": False,
            "saida_manual": False,
            "incompleto": False,
        }
    ]


# ───────────────────────────── as regras ─────────────────────────────
def _checar_dia(rot: str, t: dict, segs: list[dict], orfaos_do_dia: list[dict]) -> list[str]:
    """R1+R2+R3 sobre um turno. `rot` só entra nas mensagens."""
    d: list[str] = []
    completos = [s for s in segs if not s.get("incompleto")]
    incompletos = [s for s in segs if s.get("incompleto")]

    # R1 — um segmento completo por par, nada perdido nem duplicado
    if len(completos) != len(t["pares"]):
        d.append(f"R1 {rot}: {len(t['pares'])} par(es) no motor viraram {len(completos)} segmento(s)")

    # R2 — a soma dos completos reproduz as horas do dia (1 min de folga por par)
    soma = sum(int(s.get("minutos") or 0) for s in completos)
    folga = max(1, len(t["pares"]))
    if abs(soma - int(round(t["worked_min"]))) > folga:
        d.append(f"R2 {rot}: Σ segmentos {soma} min ≠ {int(round(t['worked_min']))} min do dia (folga {folga})")

    # R3 — órfã nomeia o que falta, uma ponta só, zero minuto inventado
    for s in incompletos:
        if not s.get("falta"):
            d.append(f"R3 {rot}: segmento incompleto sem dizer o que falta: {s}")
        if (s.get("entrada") is None) == (s.get("saida") is None):
            d.append(f"R3 {rot}: segmento incompleto com as duas pontas (ou nenhuma): {s}")
        if int(s.get("minutos") or 0) != 0:
            d.append(f"R3 {rot}: segmento incompleto com {s['minutos']} min — hora inventada: {s}")

    # R4 (parte do dia) — toda órfã do dia tem o seu segmento incompleto
    if len(incompletos) != len(orfaos_do_dia):
        d.append(f"R4 {rot}: {len(orfaos_do_dia)} batida(s) órfã(s) no dia viraram {len(incompletos)} segmento(s)")
    return d


def _motor(batidas: list[dict], janelas: list | None = None):
    """pares/turnos/órfãos por dia do plantão — a régua única, sem cópia.

    Aceita as DUAS assinaturas de propósito: na árvore SEM a P6a, `_parear`/`_agrupar_turnos`
    não recebem órfãos. Um TypeError aqui não é desvio medido, é oráculo que não rodou — e
    este oráculo precisa sair vermelho POR REGRA lá, não por exceção de import."""
    from modules.people_management.hr.services.espelho_service import _agrupar_turnos, _parear

    orfaos: list[dict] = []
    try:
        pares, anomalias = _parear(batidas, orfaos_out=orfaos)
    except TypeError:
        pares, anomalias = _parear(batidas)
    try:
        turnos = _agrupar_turnos(pares, janelas or [], orfaos)
    except TypeError:
        turnos = _agrupar_turnos(pares, janelas or [])
    por_dia: dict = {}
    for o in orfaos:
        if o.get("dia") is not None:
            por_dia.setdefault(o["dia"], []).append(o)
    return pares, turnos, por_dia, orfaos, anomalias


def _rodar_fixtures(fabrica) -> list[str]:
    """As cinco formas de dia, com `fabrica` montando os segmentos (real ou controle)."""
    d: list[str] = []
    for rot, batidas, n_completos, faltas_esp in FIXTURES:
        pares, turnos, por_dia, orfaos, _ = _motor(batidas)
        if len(turnos) != 1:
            d.append(f"R1 {rot}: o motor produziu {len(turnos)} turno(s) onde há 1 plantão")
            continue
        t = turnos[0]
        segs = fabrica(t["pares"], por_dia.get(t["date"], []))
        d += _checar_dia(rot, t, segs, por_dia.get(t["date"], []))
        if len([s for s in segs if not s.get("incompleto")]) != n_completos:
            d.append(f"R1 {rot}: esperado {n_completos} segmento(s) completo(s)")
        faltas = tuple(s.get("falta") for s in segs if s.get("incompleto"))
        if faltas != faltas_esp:
            d.append(f"R3 {rot}: faltas nomeadas {faltas} ≠ {faltas_esp}")
    return d


def _checar_em_curso(fabrica) -> list[str]:
    """R3b — quem está TRABALHANDO agora tem segmento aberto marcado `em_curso`, não pendência.

    Cobrar a saída de quem entrou há duas horas é cobrar o futuro. Sem esta marca, toda a
    escala noturna aparece todo dia como "falta a saída" e o DP não tem o que corrigir."""
    from zoneinfo import ZoneInfo

    from modules.people_management.hr.services.espelho_service import _agrupar_turnos, _parear

    agora = datetime.now(ZoneInfo("America/Manaus")).replace(tzinfo=None, second=0, microsecond=0)
    batidas = [
        {
            "punch_id": "fix-curso-0",
            "punch_type": "entrada",
            "punch_timestamp": agora - timedelta(hours=8),
            "status": "approved",
            "device_type": "mobile",
            "justification_id": "",
        },
        {
            "punch_id": "fix-curso-1",
            "punch_type": "saida",
            "punch_timestamp": agora - timedelta(hours=4),
            "status": "approved",
            "device_type": "mobile",
            "justification_id": "",
        },
        {  # abriu de novo há 2h e ainda não saiu — turno EM ANDAMENTO
            "punch_id": "fix-curso-2",
            "punch_type": "entrada",
            "punch_timestamp": agora - timedelta(hours=2),
            "status": "approved",
            "device_type": "mobile",
            "justification_id": "",
        },
    ]
    orfaos: list[dict] = []
    try:
        pares, _ = _parear(batidas, orfaos_out=orfaos)
        turnos = _agrupar_turnos(pares, [], orfaos)
    except TypeError:
        pares, _ = _parear(batidas)
        turnos = _agrupar_turnos(pares, [])
    if not turnos:
        return ["R3b: o motor não produziu turno para um plantão em andamento"]
    por_dia = {o["dia"]: [o] for o in orfaos if o.get("dia") is not None}
    segs = fabrica(turnos[-1]["pares"], por_dia.get(turnos[-1]["date"], []))
    abertos = [s for s in segs if s.get("incompleto")]
    if len(abertos) != 1:
        return [f"R3b: plantão em andamento produziu {len(abertos)} segmento(s) aberto(s), esperado 1"]
    if not abertos[0].get("em_curso"):
        return ["R3b: o segmento do turno em andamento não está marcado `em_curso` — vira pendência falsa"]
    return []


def _rodar_real(db, fabrica, mes: int, ano: int) -> tuple[list[str], int, int, int]:
    """As mesmas regras sobre o dado REAL do mês (somente leitura)."""
    from sqlalchemy import text

    from modules.people_management.hr.services.espelho_service import (
        _carregar_batidas,
        _janelas_de_turno,
        _mes_bounds,
    )

    ini, fim = _mes_bounds(mes, ano)
    emps = [
        r[0]
        for r in db.execute(
            text(
                "SELECT DISTINCT CAST(employee_id AS TEXT) FROM gp_clock_punches "
                "WHERE punch_timestamp >= :a AND punch_timestamp < :b ORDER BY 1"
            ),
            {"a": ini, "b": fim},
        ).all()
    ]
    d: list[str] = []
    n_dias = n_multi = n_inc = 0
    for emp in emps:
        batidas = _carregar_batidas(db, emp, mes, ano)
        _, turnos, por_dia, orfaos, _ = _motor(batidas, _janelas_de_turno(db, emp, mes, ano))
        turnos = [t for t in turnos if ini <= t["date"] < fim]
        dias_turno = {t["date"] for t in turnos}
        vistas = 0
        for t in turnos:
            orf = por_dia.get(t["date"], [])
            segs = fabrica(t["pares"], orf)
            n_dias += 1
            n_multi += len(segs) >= 2
            n_inc += any(s.get("incompleto") for s in segs)
            vistas += len([s for s in segs if s.get("incompleto")])
            d += _checar_dia("real", t, segs, orf)
        # R4 — órfã só pode faltar no detalhe se o dia dela não tem nenhum par válido
        sem_linha = len([o for o in orfaos if o.get("dia") not in dias_turno])
        if vistas + sem_linha != len(orfaos):
            d.append(
                f"R4 real: {len(orfaos)} órfã(s) ≠ {vistas} no detalhe + {sem_linha} em dia sem turno"
            )
    return d[:12], n_dias, n_multi, n_inc


def _rodar_contrato(db, mes: int, ano: int) -> list[str]:
    """R5+R6 — contrato de `daily_summary` e tolerância à ausência da chave.

    Grava com `calcular_espelho` e faz ROLLBACK: o que se prova é o que o motor ESCREVE, não o
    que ele retorna. Sem isto o oráculo ficaria verde sobre um `daily` que nunca chegou à
    coluna."""
    from sqlalchemy import text

    from modules.hr.time_tracking.models.time_sheet import TimeSheet
    from modules.hr.time_tracking.services.report_service import ReportService
    from modules.people_management.hr.services.espelho_service import calcular_espelho
    from modules.people_management.ponto.controllers.punch_controller import _dia_da_tela

    d: list[str] = []
    alvo = db.execute(
        text(
            "SELECT CAST(p.employee_id AS TEXT) FROM gp_clock_punches p "
            "LEFT JOIN time_sheets t ON CAST(t.employee_id AS TEXT) = CAST(p.employee_id AS TEXT) "
            " AND t.reference_month = :m AND t.reference_year = :a "
            "WHERE p.punch_timestamp >= :ini AND p.punch_timestamp < :fim "
            "  AND COALESCE(t.status, 'calculado') NOT IN "
            "      ('fechado','aprovado','revisado','enviado_folha') "
            "  AND t.closed_at IS NULL AND COALESCE(t.approved_by_employee, false) = false "
            "GROUP BY 1 HAVING count(*) >= 4 ORDER BY count(*) DESC LIMIT 1"
        ),
        {"m": mes, "a": ano, "ini": date(ano, mes, 1), "fim": date(ano + (mes == 12), mes % 12 + 1, 1)},
    ).scalar()
    if not alvo:
        d.append("R5: nenhum espelho ABERTO com batidas no mês — o contrato não foi exercido")
        return d
    try:
        calcular_espelho(db, alvo, mes, ano)
        row = (
            db.query(TimeSheet)
            .filter(
                TimeSheet.employee_id == str(alvo),
                TimeSheet.reference_month == mes,
                TimeSheet.reference_year == ano,
            )
            .first()
        )
        dias = row.daily_summary or []
        if not dias:
            d.append("R5: espelho gravado sem nenhum dia — nada a conferir")
            return d
        for dia in dias:
            faltando = [k for k in CONTRATO if k not in dia]
            if faltando:
                d.append(f"R5: chave(s) do contrato ausente(s) no daily_summary: {faltando}")
                break
        if not any("segmentos" in dia for dia in dias):
            d.append("R5: nenhum dia gravado trouxe `segmentos` — o motor ainda descarta os pares")
        # R6 — dia SEM a chave (é o que o segundo escritor grava) não pode quebrar ninguém
        sem = {k: v for k, v in dias[0].items() if k != "segmentos"}
        try:
            tela = _dia_da_tela(sem)
            if "segmentos" not in tela:
                d.append("R6: a tela deixou de expor `segmentos` — o detalhe morre no controller")
            if _dia_da_tela(dias[0]).get("segmentos") == [] and dias[0].get("segmentos"):
                d.append("R6: a tela recebeu segmentos e devolveu vazio")
        except Exception as e:  # noqa: BLE001
            d.append(f"R6: a tela quebrou num dia sem a chave `segmentos`: {e!r}")
        svc = ReportService.__new__(ReportService)
        try:
            if svc._acjef_detail_line(row, dias[0], 1) != svc._acjef_detail_line(row, sem, 1):
                d.append("R6: a linha ACJEF (arquivo de governo, largura fixa) mudou com a chave nova")
        except Exception as e:  # noqa: BLE001
            d.append(f"R6: ACJEF quebrou: {e!r}")
    finally:
        db.rollback()
    return d


def main() -> int:
    # Sem a P6a o motor não tem `_segmentos`: cai num fabricante que devolve NADA, e aí as
    # regras reprovam por REGRA (R1: N pares viraram 0 segmentos), não por ImportError.
    try:
        from modules.people_management.hr.services.espelho_service import _segmentos
    except ImportError:
        def _segmentos(pares, orfaos):  # noqa: ANN001, ANN202
            return []

    mes, ano = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (9, 2026)
    desvios: list[str] = []

    print("── fixtures (as cinco formas de dia, em memória) ──")
    d = _rodar_fixtures(_segmentos)
    desvios += d
    print(f"  {'✗' if d else '✓'} {len(FIXTURES)} forma(s) de dia · {len(d)} desvio(s)")

    d = _checar_em_curso(_segmentos)
    desvios += d
    print(f"  {'✗' if d else '✓'} turno em andamento marcado `em_curso` · {len(d)} desvio(s)")

    print("── controle: as mesmas regras contra o comportamento ANTERIOR ──")
    controle = _rodar_fixtures(_segmentos_da_linha_unica) + _checar_em_curso(_segmentos_da_linha_unica)
    if not controle:
        desvios.append(
            "CONTROLE: a linha única (comportamento anterior) passou nas regras — "
            "o oráculo está medindo o nada"
        )
        print("  ✗ a linha única passou — oráculo cúmplice")
    else:
        print(f"  ✓ a linha única reprova em {len(controle)} ponto(s), ex.: {controle[0]}")

    from core.database.session import SyncSessionLocal

    db = SyncSessionLocal()
    try:
        print(f"── dado real {mes:02d}/{ano} (somente leitura) ──")
        d, n_dias, n_multi, n_inc = _rodar_real(db, _segmentos, mes, ano)
        desvios += d
        print(
            f"  {'✗' if d else '✓'} {n_dias} dia(s) · {n_multi} com 2+ segmentos · "
            f"{n_inc} com segmento incompleto · {len(d)} desvio(s)"
        )
        if n_dias and not n_multi:
            desvios.append("R1 real: nenhum dia do mês tem 2+ segmentos — a linha única não teria mudado nada")

        print("── contrato de daily_summary + tolerância à ausência (rollback) ──")
        d = _rodar_contrato(db, mes, ano)
        desvios += d
        print(f"  {'✗' if d else '✓'} {len(d)} desvio(s)")
    finally:
        db.rollback()
        db.close()

    for x in desvios:
        print(f"  ✗ {x}")
    print(f"\nTOTAL: {len(desvios)} regra(s) de segmento violada(s)")
    return 1 if desvios else 0


if __name__ == "__main__":
    sys.exit(main())
