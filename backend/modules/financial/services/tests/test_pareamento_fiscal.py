from modules.financial.services.pareamento_fiscal_service import _status_linha


def test_bate_dentro_da_tolerancia():
    diff, bate = _status_linha(1000.00, 1000.01)
    assert bate is True and abs(diff) <= 0.02


def test_diverge_fora_da_tolerancia():
    diff, bate = _status_linha(1000.00, 1050.00)
    assert bate is False and diff == -50.00


def test_portte_ausente_nao_bate():
    diff, bate = _status_linha(1000.00, None)
    assert bate is False


def test_ambos_ausentes_nao_bate():
    diff, bate = _status_linha(None, None)
    assert bate is False


from modules.financial.services.pareamento_fiscal_service import _inss_total


def test_inss_total_soma_segurado_mais_288pct():
    # segurado 7111.43 + base 86400 * 0.288 = 7111.43 + 24883.20 = 31994.63
    assert _inss_total(7111.43, 86400.0) == 31994.63


def test_inss_total_sem_base_retorna_none():
    assert _inss_total(500.0, 0) is None
    assert _inss_total(500.0, None) is None
