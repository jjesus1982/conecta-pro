"""Oráculo: o dia com dois turnos chega à tela como DOIS, não como um.

A REGRA que este arquivo guarda (não a fotografia de nenhum mês, pessoa ou id):

  1. Dia cujo motor devolve 2+ pares fechados SAI da tela com as quatro colunas de hora
     preenchidas — e `saida1` é a saída do PRIMEIRO par, não a última do dia. Era aqui o
     defeito: `_dia_da_tela` devolvia `entrada2`/`saida2` fixos em `""`, e um plantão
     19:00→02:00 + 03:00→07:17 aparecia como "19:00 → 07:17", com o intervalo sumido.
  2. Nada é escondido em silêncio: com 3+ segmentos visíveis, `obs` traz a marca; batida
     repetida (mesma hora de um par fechado) sai das colunas mas é CONTADA no aviso; e um
     par incompleto faz o dia aparecer COMO quebrado.
  3. `saldo_dia` é `trabalhadas − previsto` — a mesma subtração do mês, não uma conta nova.
  4. Sobre dado REAL: na competência corrente, nenhum dia com 2+ pares chega à tela com a
     segunda coluna vazia. É a regra do item 1 medida contra o banco em vez de fixture.

Por que 4 existe junto de 1: o `daily_summary` gravado NÃO tem a chave `segmentos` (0 de 295
time_sheets no dia em que isto foi escrito) — quem a preenche é `dias_com_segmentos`, derivando
do motor. Um oráculo que só olhasse fixture passaria com a derivação desligada.

Roda no container:
    docker exec -e PYTHONPATH=/app -w /app conecta-pro-backend python scripts/orq/test_apropriacao_segmentos_na_tela.py
"""

import asyncio

from sqlalchemy import text

from core.database import async_session_factory
from core.database.session import SyncSessionLocal
from modules.people_management.hr.services.espelho_ponto_service import ler_espelho
from modules.people_management.hr.services.espelho_service import segmentos_do_mes
from modules.people_management.ponto.controllers.punch_controller import (
    _dia_da_tela,
    _tem_intervalo,
    dias_com_segmentos,
)


def _par(entrada: str, saida: str, minutos: int) -> dict:
    return {"entrada": entrada, "saida": saida, "minutos": minutos, "incompleto": False}


def _orfao(lado: str, hora: str) -> dict:
    return {
        "entrada": hora if lado == "entrada" else None,
        "saida": None if lado == "entrada" else hora,
        "minutos": 0,
        "incompleto": True,
        "falta": "saida" if lado == "entrada" else "entrada",
    }


def regra_1_dois_turnos_duas_linhas() -> None:
    """2 pares ⇒ 4 colunas preenchidas, e a coluna 2 fecha no fim do dia."""
    dia = {
        "date": "2026-09-03",
        "entrada": "19:00",
        "saida": "07:17",  # a saída CONSOLIDADA do dia (o motor junta a virada de meia-noite)
        "intervalo": "01:00",
        "worked": 661,
        "expected": 660,
        "segmentos": [_par("19:00", "02:00", 420), _par("03:00", "07:17", 257)],
    }
    r = _dia_da_tela(dia)
    assert r["entrada1"] == "19:00", r
    assert r["saida1"] == "02:00", f"saida1 tem de ser a saída do 1º par, veio {r['saida1']!r}"
    assert r["entrada2"] == "03:00", f"segundo turno invisível: entrada2={r['entrada2']!r}"
    assert r["saida2"] == "07:17", r
    assert r["intervalo"] == "01:00", r
    assert len(r["segmentos"]) == 2, r
    print("OK 1 · 19:00→02:00 e 03:00→07:17 saem nas quatro colunas (e não como 19:00→07:17)")


def regra_2_nada_escondido_em_silencio() -> None:
    """3+ segmentos, batida repetida e par incompleto têm de APARECER no aviso."""
    tres = _dia_da_tela(
        {
            "date": "2026-09-10",
            "entrada": "08:00",
            "saida": "20:00",
            "worked": 600,
            "expected": 480,
            "segmentos": [
                _par("08:00", "12:00", 240),
                _par("13:00", "17:00", 240),
                _par("18:00", "20:00", 120),
            ],
        }
    )
    assert "segmento" in tres["obs"], f"3º segmento sumiu sem marca: obs={tres['obs']!r}"

    # batida repetida: órfão na MESMA hora de um par fechado é ruído do aparelho — sai das
    # colunas (senão o único par de verdade cai fora da tela) mas é contado.
    rep = _dia_da_tela(
        {
            "date": "2026-09-08",
            "entrada": "08:01",
            "saida": "12:00",
            "worked": 239,
            "expected": 480,
            "segmentos": [_orfao("entrada", "08:01"), _orfao("entrada", "08:01"), _par("08:01", "12:00", 239)],
        }
    )
    assert (rep["entrada1"], rep["saida1"]) == ("08:01", "12:00"), rep
    assert "repetida" in rep["obs"], f"batida repetida não avisada: obs={rep['obs']!r}"

    quebrado = _dia_da_tela(
        {
            "date": "2026-09-17",
            "entrada": "08:00",
            "saida": "12:01",
            "worked": 241,
            "expected": 480,
            "segmentos": [_par("08:00", "12:01", 241), _orfao("entrada", "13:00")],
        }
    )
    assert quebrado["entrada2"] == "13:00", quebrado
    assert quebrado["saida2"] == "", quebrado
    assert "quebrado" in quebrado["obs"], f"dia quebrado passou por normal: obs={quebrado['obs']!r}"
    print("OK 2 · 3+ segmentos, batida repetida e par incompleto todos com marca em obs")


def regra_3_saldo_do_dia() -> None:
    r = _dia_da_tela({"date": "2026-09-03", "worked": 661, "expected": 660, "segmentos": []})
    assert r["saldo_min"] == 1 and r["saldo_dia"] == "00:01", r
    neg = _dia_da_tela({"date": "2026-09-04", "worked": 239, "expected": 480, "segmentos": []})
    assert neg["saldo_min"] == -241 and neg["saldo_dia"] == "-04:01", neg
    sem = _dia_da_tela({"date": "2026-09-05", "segmentos": []})
    assert sem["saldo_min"] is None and sem["saldo_dia"] == "—", sem
    print("OK 3 · saldo_dia = trabalhadas − previsto (e '—' quando não há número, nunca 0)")


async def regra_4_dado_real() -> None:
    """No banco: nenhum dia com 2+ pares chega à tela com a segunda coluna vazia."""
    async with async_session_factory() as db:
        comp = (
            await db.execute(
                text(
                    "SELECT reference_year, reference_month FROM time_sheets "
                    " WHERE coalesce(is_deleted,false)=false GROUP BY 1,2 "
                    " ORDER BY count(*) DESC, 1 DESC, 2 DESC LIMIT 1"
                )
            )
        ).first()
    assert comp, "nenhum time_sheet no banco — oráculo sem lastro"
    ano, mes = int(comp[0]), int(comp[1])

    com_dois = perdidos = 0
    with SyncSessionLocal() as s:
        ids = [
            r[0]
            for r in s.execute(
                text(
                    "SELECT CAST(employee_id AS TEXT) FROM time_sheets "
                    " WHERE reference_month=:m AND reference_year=:y AND coalesce(is_deleted,false)=false"
                ),
                {"m": mes, "y": ano},
            ).all()
        ]
        for eid in ids:
            esp = ler_espelho(s, eid, mes, ano)
            if esp is None:
                continue
            for d in dias_com_segmentos(s, esp, mes, ano):
                pares = [x for x in (d.get("segmentos") or []) if not x.get("incompleto")]
                if len(pares) < 2:
                    continue
                com_dois += 1
                linha = _dia_da_tela(d)
                if not linha["entrada2"] or not linha["saida2"]:
                    perdidos += 1
        # a derivação tem de estar VIVA: se ninguém tem 2+ pares, o motor não está sendo lido
        derivados = sum(
            1 for eid in ids[:5] for _ in segmentos_do_mes(s, eid, mes, ano).values()
        )
    assert com_dois > 0, (
        f"{mes:02d}/{ano}: nenhum dia com 2+ pares — a derivação de segmentos está desligada "
        f"(amostra de 5 colaboradores devolveu {derivados} dia(s) do motor)"
    )
    assert perdidos == 0, f"{perdidos} de {com_dois} dias com 2+ pares chegaram à tela sem a 2ª coluna"
    print(f"OK 4 · {mes:02d}/{ano}: {com_dois} dia(s) com 2+ pares, {perdidos} perdido(s) na tela")


def regra_5_intervalo_sem_segundo_par_avisa() -> None:
    """Dia cujo espelho REGISTRA intervalo não pode chegar como UMA linha calada.

    A régua: se a linha gravada subtraiu intervalo, o dia TEM dois segmentos — então ou as quatro
    colunas saem preenchidas, ou a Obs declara a ausência. Nunca uma linha única muda.

    Por que a regra 4 não pega isto: ela só visita dias cuja DERIVAÇÃO devolveu 2+ pares. Quando
    a derivação devolve 1, ela nem olha — e é justamente aí que a tela calava (medido em 28/09:
    21 de 1299 linhas com `intervalo 01:00`, uma coluna de par e Obs vazia).
    """
    mudo = _dia_da_tela(
        {
            "date": "2026-08-12",
            "entrada": "19:01",
            "saida": "07:00",
            "intervalo": "01:00",
            "worked": 659,
            "expected": 660,
            "segmentos": [_par("19:01", "07:00", 659)],
        }
    )
    assert "recalcule" in mudo["obs"], (
        f"dia com intervalo no espelho e UM par só chegou sem aviso: obs={mudo['obs']!r}"
    )
    # CONTROLE (irmã de caminho feliz): com os dois pares à vista, nada de aviso — uma regra que
    # avisa sempre não prova nada.
    dois = _dia_da_tela(
        {
            "date": "2026-08-12",
            "intervalo": "01:00",
            "worked": 659,
            "expected": 660,
            "segmentos": [_par("19:01", "00:00", 299), _par("01:00", "07:00", 360)],
        }
    )
    assert dois["obs"] == "", f"dia completo ganhou aviso indevido: obs={dois['obs']!r}"
    # CONTROLE: um par e SEM intervalo é jornada corrida legítima — também cala.
    corrido = _dia_da_tela(
        {
            "date": "2026-08-12",
            "intervalo": "00:00",
            "worked": 720,
            "expected": 660,
            "segmentos": [_par("19:01", "07:01", 720)],
        }
    )
    assert corrido["obs"] == "", f"jornada corrida ganhou aviso indevido: obs={corrido['obs']!r}"

    # Sessão SÍNCRONA de propósito: a regra 4 já gastou um `asyncio.run`, e um segundo loop
    # reaproveitaria o mesmo pool async já fechado ("attached to a different loop"). O sujeito
    # (competência) sai por SELECT, não fica escrito aqui — a régua não apodrece quando o mês virar.
    com_intervalo = mudos = 0
    with SyncSessionLocal() as s:
        comp = s.execute(
            text(
                "SELECT reference_year, reference_month FROM time_sheets "
                " WHERE coalesce(is_deleted,false)=false GROUP BY 1,2 "
                " ORDER BY count(*) DESC, 1 DESC, 2 DESC LIMIT 1"
            )
        ).first()
        assert comp, "nenhum time_sheet no banco — oráculo sem lastro"
        ano, mes = int(comp[0]), int(comp[1])
        ids = [
            r[0]
            for r in s.execute(
                text(
                    "SELECT CAST(employee_id AS TEXT) FROM time_sheets "
                    " WHERE reference_month=:m AND reference_year=:y AND coalesce(is_deleted,false)=false"
                ),
                {"m": mes, "y": ano},
            ).all()
        ]
        for eid in ids:
            esp = ler_espelho(s, eid, mes, ano)
            if esp is None:
                continue
            for d in dias_com_segmentos(s, esp, mes, ano):
                if not _tem_intervalo(d.get("intervalo")):
                    continue
                com_intervalo += 1
                linha = _dia_da_tela(d)
                se_ve_dois = bool(linha["entrada2"] and linha["saida2"])
                if not se_ve_dois and not linha["obs"]:
                    mudos += 1
    assert com_intervalo > 0, (
        f"{mes:02d}/{ano}: nenhum dia com intervalo gravado — sem lastro para a régua"
    )
    assert mudos == 0, (
        f"{mudos} de {com_intervalo} dia(s) com intervalo no espelho chegaram à tela como UMA "
        f"linha, sem 2º par e sem nenhum aviso"
    )
    print(
        f"OK 5 · {mes:02d}/{ano}: {com_intervalo} dia(s) com intervalo gravado, "
        f"{mudos} chegaram calados à tela"
    )


def main() -> None:
    regra_1_dois_turnos_duas_linhas()
    regra_2_nada_escondido_em_silencio()
    regra_3_saldo_do_dia()
    asyncio.run(regra_4_dado_real())
    regra_5_intervalo_sem_segundo_par_avisa()
    print("TODOS OS ORÁCULOS OK")


if __name__ == "__main__":
    main()
