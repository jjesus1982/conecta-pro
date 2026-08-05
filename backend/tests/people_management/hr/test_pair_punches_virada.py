"""Especificação executável do pareamento de batidas nas TELAS DE RH.

Contexto: existem TRÊS pareadores de batida no sistema. Dois foram alinhados na
Task 3 da frente folha (commit 9dd89246): `ponto/services/horas_service.parear_batidas`
(canônico, cronológico) e `ponto/services/punch_service` (passou a delegar). O terceiro,
`hr/services/time_record_service._pair_punches`, não foi alcançado.

Este arquivo é a spec do redesenho do terceiro. Os `xfail(strict=True)` são os defeitos
MEDIDOS que ele precisa fechar — quando um deles passar, o pytest FALHA de propósito,
obrigando quem consertou a remover o marcador. Os testes sem marcador são guardas de
regressão: já passam hoje e não podem quebrar.

Tentativa de correção em 2026-08-05 (commit 5e0bbc1f) foi REVERTIDA: parear
cronologicamente sem noção de direção fabricava turno de 12h sobre o período de
descanso. Ver docs/superpowers/plans/ para o plano do redesenho.

Rodar:
    cd /opt/conecta-pro/backend && venv/bin/python -m pytest tests/people_management/hr/test_pair_punches_virada.py -v
"""

from datetime import datetime

import pytest

from modules.people_management.hr.services.time_record_service import TimeRecordService


def _punch(emp: str, ts: str, tipo: str, pid: str = "p1"):
    """Linha de gp_clock_punches como o SELECT do service a devolve."""
    return {
        "id": pid,
        "punch_id": pid,
        "employee_id": emp,
        "punch_type": tipo,
        "punch_timestamp": datetime.fromisoformat(ts),
        "status": "aprovado",
        "latitude": None,
        "longitude": None,
        "device_type": "portal",
        "created_at": datetime.fromisoformat(ts),
    }


# ---------------------------------------------------------------------------
# DEFEITOS MEDIDOS — o redesenho tem de fechar estes.
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="DEFEITO: _pair_punches agrupa por (funcionario, DIA) antes de parear, "
    "entao o plantao 12x36 noturno vira dois registros quebrados. "
    "Medido julho/2026: 240 de 853 dias-funcionario (28%).",
)
def test_plantao_noturno_vira_um_registro_no_dia_da_entrada():
    """21:00 do dia 10 -> 09:00 do dia 11 = UM registro, datado no dia 10, 12h."""
    rows = [
        _punch("emp-1", "2026-07-10T21:00:00", "entrada", "a"),
        _punch("emp-1", "2026-07-11T09:00:00", "saida", "b"),
    ]

    recs = TimeRecordService(None)._pair_punches(rows)

    assert len(recs) == 1, f"esperado 1 registro, veio {len(recs)}: {recs}"
    r = recs[0]
    assert r["record_date"] == "2026-07-10"
    assert r["clock_in"] == "21:00"
    assert r["clock_out"] == "09:00"
    assert r["total_hours"] == "12:00"
    assert r["status"] == "regular"


@pytest.mark.xfail(
    strict=True,
    reason="DEFEITO: mesmo do anterior, com dois funcionarios — o turno de cada um "
    "cruza a meia-noite e some.",
)
def test_dois_funcionarios_no_noturno_nao_se_misturam():
    """Pareamento e por funcionario. A batida de um nunca fecha o turno do outro."""
    rows = [
        _punch("emp-A", "2026-07-10T21:00:00", "entrada", "a"),
        _punch("emp-B", "2026-07-10T22:00:00", "entrada", "b"),
        _punch("emp-A", "2026-07-11T09:00:00", "saida", "c"),
        _punch("emp-B", "2026-07-11T10:00:00", "saida", "d"),
    ]

    recs = TimeRecordService(None)._pair_punches(rows)

    por_emp = {r["employee_id"]: r for r in recs}
    assert por_emp["emp-A"]["clock_in"] == "21:00"
    assert por_emp["emp-A"]["clock_out"] == "09:00"
    assert por_emp["emp-B"]["clock_in"] == "22:00"
    assert por_emp["emp-B"]["clock_out"] == "10:00"


@pytest.mark.xfail(
    strict=True,
    reason="DEFEITO (nunca fabricar): numa janela de UM dia civil, as batidas de um "
    "noturno sao [saida de ontem, entrada de hoje] — duas pontas de turnos DIFERENTES. "
    "O pareador junta as duas e inventa 12h de trabalho sobre o periodo de DESCANSO. "
    "get_daily filtra exatamente um dia civil (time_record_service.py:919-929), entao "
    "isso dispara estruturalmente para todo plantonista noturno.",
)
def test_janela_de_um_dia_do_noturno_nao_fabrica_turno():
    """Duas pontas soltas NAO podem virar um turno. No maximo, dois registros parciais."""
    rows = [
        _punch("emp-N", "2026-07-11T09:00:00", "saida", "a"),  # fim do turno de ontem
        _punch("emp-N", "2026-07-11T21:00:00", "entrada", "b"),  # inicio do turno de hoje
    ]

    recs = TimeRecordService(None)._pair_punches(rows)

    for r in recs:
        fechado = r["clock_in"] and r["clock_out"]
        assert not (fechado and r["total_hours"] == "12:00"), (
            "turno FABRICADO sobre o descanso: as duas batidas sao de turnos diferentes. "
            f"registro={r}"
        )


# ---------------------------------------------------------------------------
# GUARDAS DE REGRESSAO — passam hoje, nao podem quebrar no redesenho.
# ---------------------------------------------------------------------------


def test_turno_diurno_com_almoco_continua_funcionando():
    """Jornada 08-12 / 13-17 com almoco: um registro, 8h liquidas."""
    rows = [
        _punch("emp-2", "2026-07-10T08:00:00", "entrada", "a"),
        _punch("emp-2", "2026-07-10T12:00:00", "saida_almoco", "b"),
        _punch("emp-2", "2026-07-10T13:00:00", "retorno_almoco", "c"),
        _punch("emp-2", "2026-07-10T17:00:00", "saida", "d"),
    ]

    recs = TimeRecordService(None)._pair_punches(rows)

    assert len(recs) == 1, f"esperado 1 registro, veio {len(recs)}: {recs}"
    r = recs[0]
    assert r["record_date"] == "2026-07-10"
    assert r["clock_in"] == "08:00"
    assert r["clock_out"] == "17:00"
    assert r["clock_in_lunch"] == "12:00"
    assert r["clock_out_lunch"] == "13:00"
    assert r["total_hours"] == "08:00"  # 9h de janela - 1h de almoco


def test_batida_orfa_nao_desalinha_o_resto():
    """Uma batida sem par nao pode embaralhar os dias seguintes."""
    rows = [
        _punch("emp-3", "2026-07-10T08:00:00", "entrada", "a"),  # orfa: esqueceu a saida
        _punch("emp-3", "2026-07-11T08:00:00", "entrada", "b"),
        _punch("emp-3", "2026-07-11T17:00:00", "saida", "c"),
    ]

    recs = TimeRecordService(None)._pair_punches(rows)

    dias = {r["record_date"]: r for r in recs}
    assert "2026-07-11" in dias, f"dia 11 nao pareou: {recs}"
    assert dias["2026-07-11"]["clock_in"] == "08:00"
    assert dias["2026-07-11"]["clock_out"] == "17:00"
    assert dias["2026-07-11"]["total_hours"] == "09:00"


def test_entrada_sem_saida_vira_inconsistencia():
    """Quem bateu entrada e nao bateu saida NAO pode sumir da tela.

    O DP fecha ponto aberto por esta linha: a tela usa `!item.saida` para mostrar o
    botao 'Saida' (frontend/src/app/modulos/dp/ponto/page.tsx:566). Se o registro some,
    o ponto aberto fica invisivel e nunca e fechado.
    """
    rows = [_punch("emp-4", "2026-07-10T08:00:00", "entrada", "c")]

    recs = TimeRecordService(None)._pair_punches(rows)

    assert len(recs) == 1, f"a pessoa sumiu da tela: {recs}"
    r = recs[0]
    assert r["clock_in"] == "08:00"
    assert r["clock_out"] is None
    assert r["status"] == "inconsistencia"
