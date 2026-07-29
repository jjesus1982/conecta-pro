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
