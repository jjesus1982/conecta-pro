"""Pareamento de batidas na VIRADA DE DIA — 3ª implementação (telas de RH).

O plantão 12x36 noturno entra 21:00 e sai 09:00 do dia seguinte. `_pair_punches`
agrupava por (funcionário, DIA) ANTES de parear, então o plantão virava dois dias
quebrados: um só com entrada, outro só com saída. Medido em julho/2026: 240 de 853
dias-funcionário (28%).

O par conta no dia da ENTRADA — mesma convenção de horas_service.parear_batidas.

Rodar no container:
    docker exec conecta-pro-backend python3 -m pytest tests/people_management/hr/test_pair_punches_virada.py -v
"""

from datetime import datetime

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


def test_turno_diurno_com_almoco_continua_funcionando():
    """Regressão: o caso que já funcionava não pode quebrar."""
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
    """Uma batida sem par avança UMA posição, não duas (senão embaralha o mês)."""
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


def test_dois_funcionarios_nao_se_misturam():
    """Pareamento é por funcionário. A batida de um nunca fecha o turno do outro."""
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
