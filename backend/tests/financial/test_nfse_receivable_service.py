from modules.financial.services.nfse_receivable_service import _so_digitos, _vencimento_de


def test_vencimento_e_dia_10_do_mes_seguinte():
    # competência 07/2026 → paga em agosto (regra do Jordan)
    assert _vencimento_de("07/2026", 10).isoformat() == "2026-08-10"


def test_vencimento_vira_o_ano():
    assert _vencimento_de("12/2026", 10).isoformat() == "2027-01-10"


def test_vencimento_aceita_formato_iso():
    assert _vencimento_de("2026-07", 10).isoformat() == "2026-08-10"


def test_vencimento_invalido_devolve_none():
    assert _vencimento_de("", 10) is None
    assert _vencimento_de("lixo", 10) is None
    assert _vencimento_de("13/2026", 10) is None


def test_so_digitos_normaliza_cnpj():
    assert _so_digitos("35.710.481/0001-03") == "35710481000103"
    assert _so_digitos(None) == ""
