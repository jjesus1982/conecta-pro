"""Especificação executável do pareamento de batidas nas TELAS DE RH.

Contexto: existem TRÊS pareadores de batida no sistema. Dois foram alinhados na
Task 3 da frente folha (commit 9dd89246): `ponto/services/horas_service.parear_batidas`
(canônico, cronológico) e `ponto/services/punch_service` (passou a delegar). O terceiro,
`hr/services/time_record_service._pair_punches`, não foi alcançado.

Este arquivo é a spec do terceiro pareador. Os 3 primeiros testes eram `xfail(strict)`
documentando defeitos medidos; foram fechados pelo pareamento DIRECIONAL (Task 1 do
plano 2026-08-05-redesenho-pareamento-telas-rh). Os demais são guardas de regressão.

Tentativa de correção em 2026-08-05 (commit 5e0bbc1f) foi REVERTIDA: parear
cronologicamente sem noção de direção fabricava turno de 12h sobre o período de
descanso. Ver docs/superpowers/plans/ para o plano do redesenho.

Rodar:
    cd /opt/conecta-pro/backend && venv/bin/python -m pytest tests/people_management/hr/test_pair_punches_virada.py -v
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


# ---------------------------------------------------------------------------
# DEFEITOS FECHADOS pelo pareamento direcional — nao podem voltar.
# ---------------------------------------------------------------------------


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
# HORA EXTRA POR ESCALA — decisao do Jordan em 2026-08-06.
# ---------------------------------------------------------------------------


def test_plantao_12x36_nao_gera_hora_extra():
    """Decisao Jordan 2026-08-06: a CCT compensa o 12x36 por ESCALA, nao por sobrejornada.

    O plantao tem 12h por natureza; as 4h alem das 8h de referencia nao sao trabalho
    extraordinario. Sem esta regra, um agente 12x36 aparecia com ~+60h/mes de hora extra
    na tela do RH -- numero que a folha nao paga e que induziria o DP ao erro.
    """
    rows = [
        _punch("emp-15", "2026-07-10T19:00:00", "entrada", "a"),
        _punch("emp-15", "2026-07-11T07:00:00", "saida", "b"),
    ]

    recs = TimeRecordService(None)._pair_punches(rows, escalas={"emp-15": "12x36"})

    assert recs[0]["total_hours"] == "12:00", "as HORAS trabalhadas continuam reais"
    assert recs[0]["overtime_hours"] is None, "12x36 nao gera hora extra"


def test_escala_44h_continua_gerando_hora_extra():
    """A regra e do 12x36. Quem e 44h e ficou 10h fez 2h extras DE VERDADE."""
    rows = [
        _punch("emp-16", "2026-07-10T08:00:00", "entrada", "a"),
        _punch("emp-16", "2026-07-10T18:00:00", "saida", "b"),
    ]

    recs = TimeRecordService(None)._pair_punches(rows, escalas={"emp-16": "44h"})

    assert recs[0]["total_hours"] == "10:00"
    assert recs[0]["overtime_hours"] == "02:00"


def test_escala_desconhecida_nao_inventa_hora_extra():
    """Sem escala cadastrada, segue a convencao da folha: trata como 12x36.

    `calculo_service` resolve com `escala = emp[3] or "12x36"`. Adotar o mesmo default
    aqui evita que um cadastro incompleto (1 funcionario ativo com escala_padrao nula em
    2026-08-06) vire hora extra fantasma na tela.
    """
    rows = [
        _punch("emp-17", "2026-07-10T19:00:00", "entrada", "a"),
        _punch("emp-17", "2026-07-11T07:00:00", "saida", "b"),
    ]

    recs = TimeRecordService(None)._pair_punches(rows)  # sem mapa de escalas

    assert recs[0]["total_hours"] == "12:00"
    assert recs[0]["overtime_hours"] is None


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


def test_jornada_com_almoco_sem_tipo_de_almoco_e_um_dia_so():
    """A base REAL so tem 'entrada' e 'saida' — nao existe 'saida_almoco'.

    Medido em julho/2026: 1171 batidas 'entrada' + 1075 'saida', ZERO de almoco. Detectar
    almoco pelo TIPO e codigo morto em producao: a jornada 07-11 / 12-16 virava dois
    registros de 4h no mesmo dia (401 dos 754 dias-funcionario), e o contador de dias
    trabalhados inflava ~55%. O almoco tem de ser reconhecido pelo INTERVALO CURTO.
    """
    rows = [
        _punch("emp-8", "2026-07-31T07:00:00", "entrada", "a"),
        _punch("emp-8", "2026-07-31T11:00:00", "saida", "b"),
        _punch("emp-8", "2026-07-31T12:00:00", "entrada", "c"),
        _punch("emp-8", "2026-07-31T16:00:00", "saida", "d"),
    ]

    recs = TimeRecordService(None)._pair_punches(rows)

    assert len(recs) == 1, f"dia partido em {len(recs)} registros: {recs}"
    r = recs[0]
    assert r["clock_in"] == "07:00"
    assert r["clock_out"] == "16:00"
    assert r["clock_in_lunch"] == "11:00"
    assert r["clock_out_lunch"] == "12:00"
    assert r["total_hours"] == "08:00"  # 9h de janela - 1h de intervalo


def test_intervalo_longo_nao_vira_almoco():
    """8h entre dois turnos sao DOIS turnos, nao um almoco de 8h."""
    rows = [
        _punch("emp-9", "2026-07-10T08:00:00", "entrada", "a"),
        _punch("emp-9", "2026-07-10T12:00:00", "saida", "b"),
        _punch("emp-9", "2026-07-10T20:00:00", "entrada", "c"),
        _punch("emp-9", "2026-07-10T21:00:00", "saida", "d"),
    ]

    recs = TimeRecordService(None)._pair_punches(rows)

    for r in recs:
        assert not (r["clock_in"] == "08:00" and r["clock_out"] == "21:00"), (
            f"intervalo de 8h virou almoco — pessoa aparece 13h em servico: {r}"
        )


def test_plantao_noturno_nao_absorve_o_descanso_como_almoco():
    """36h de descanso entre plantoes nunca podem virar intervalo do mesmo turno."""
    rows = [
        _punch("emp-10", "2026-07-10T19:00:00", "entrada", "a"),
        _punch("emp-10", "2026-07-11T07:00:00", "saida", "b"),
        _punch("emp-10", "2026-07-12T19:00:00", "entrada", "c"),
        _punch("emp-10", "2026-07-13T07:00:00", "saida", "d"),
    ]

    recs = TimeRecordService(None)._pair_punches(rows)

    assert len(recs) == 2, f"os dois plantoes viraram {len(recs)} registro(s): {recs}"
    assert {r["record_date"] for r in recs} == {"2026-07-10", "2026-07-12"}
    assert all(r["total_hours"] == "12:00" for r in recs)


def test_turno_da_virada_de_mes_conta_no_mes_da_entrada():
    """31/07 21:00 -> 01/08 09:00 pertence a JULHO (mes da ENTRADA).

    O pareador nao filtra por mes -- quem filtra e o SQL de quem o chama. Este teste
    trava a convencao: se o par fosse datado pela SAIDA, o turno da virada seria contado
    em agosto (e, com a janela do SQL alargada, contado nos DOIS meses).
    """
    rows = [
        _punch("emp-11", "2026-07-31T21:00:00", "entrada", "a"),
        _punch("emp-11", "2026-08-01T09:00:00", "saida", "b"),
    ]

    recs = TimeRecordService(None)._pair_punches(rows)

    assert len(recs) == 1, f"esperado 1 registro, veio {len(recs)}: {recs}"
    assert recs[0]["record_date"] == "2026-07-31"
    assert recs[0]["total_hours"] == "12:00"


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


def test_registro_sabe_quais_batidas_consumiu():
    """get_by_id precisa achar o turno que CONTEM a batida pedida, nao `records[0]`.

    Os registros sao chaveados pela batida de ENTRADA, entao pedir a batida de SAIDA
    nao acha registro nenhum por id. Com dois turnos no mesmo dia, `records[0]` devolvia
    um turno arbitrario -- pedia-se um e recebia-se o outro.
    """
    rows = [
        _punch("emp-12", "2026-07-10T08:00:00", "entrada", "a"),
        _punch("emp-12", "2026-07-10T12:00:00", "saida", "b"),
        _punch("emp-12", "2026-07-10T18:00:00", "entrada", "c"),
        _punch("emp-12", "2026-07-10T22:00:00", "saida", "d"),
    ]

    recs = TimeRecordService(None)._pair_punches(rows, manter_origem=True)

    assert len(recs) == 2, f"6h de intervalo nao e almoco — esperado 2 turnos: {recs}"
    por_batida = {pid: r for r in recs for pid in r["_punch_ids"]}
    assert por_batida["a"]["clock_in"] == "08:00"
    assert por_batida["b"]["clock_in"] == "08:00"  # a SAIDA acha o turno da manha
    assert por_batida["c"]["clock_in"] == "18:00"
    assert por_batida["d"]["clock_in"] == "18:00"  # e nao o turno da manha


class _FakeResult:
    """Resultado minimo de db.execute para os testes do resumo mensal."""

    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return None  # _get_employee_name -> sem nome


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _sql, _params=None):
        return _FakeResult(self._rows)


async def test_resumo_mensal_conta_dias_distintos_nao_turnos():
    """Dois turnos no mesmo dia sao UM dia trabalhado.

    Ate a Task 1 cada dia civil gerava exatamente um registro, entao somar registros
    equivalia a somar dias. Agora registro = TURNO: quem trabalha manha e noite gera dois,
    e o contador inflava. Medido em julho/2026: 769 registros para 724 dias-funcionario
    reais, com ate +5 dias fantasma por pessoa no mes. A convencao correta e a do pareador
    canonico (horas_service.parear_batidas): contar datas DISTINTAS.
    """
    rows = [
        _punch("emp-14", "2026-07-10T08:00:00", "entrada", "a"),
        _punch("emp-14", "2026-07-10T12:00:00", "saida", "b"),
        _punch("emp-14", "2026-07-10T18:00:00", "entrada", "c"),  # 6h depois: outro turno
        _punch("emp-14", "2026-07-10T22:00:00", "saida", "d"),
    ]

    svc = TimeRecordService(_FakeDB(rows))
    resumo = await svc._calculate_summary_from_punches("emp-14", 7, 2026)

    assert resumo["total_worked_days"] == 1, (
        f"dois turnos no mesmo dia contaram como {resumo['total_worked_days']} dias"
    )
    assert resumo["total_hours_worked"] == "08:00"  # 4h + 4h, as horas somam normalmente


def test_origem_das_batidas_nao_vaza_no_contrato_padrao():
    """`_punch_ids` e interno: nunca pode aparecer na resposta da API."""
    rows = [
        _punch("emp-13", "2026-07-10T08:00:00", "entrada", "a"),
        _punch("emp-13", "2026-07-10T17:00:00", "saida", "b"),
    ]

    recs = TimeRecordService(None)._pair_punches(rows)

    assert recs, "sem registro para conferir"
    for r in recs:
        assert "_punch_ids" not in r, f"chave interna vazou no contrato: {sorted(r)}"


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
