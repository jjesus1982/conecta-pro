"""Helpers de pareamento fiscal nosso × Portte (Fase 5).

A tela `pareamento-tributos` (async) faz a comparação inline; aqui ficam só as duas
funções puras que ela reusa (testáveis sem banco). Verdade = Portte; oráculo: valor
sem guia = None (a tela mostra "aguardando"), nunca zero.
"""
from __future__ import annotations

TOL = 0.02  # tolerância de 2 centavos (arredondamento)

# Lucro Real: a guia INSS (DARF DCTFWeb) é o INSS TOTAL, não só o do empregado.
# Mesmas alíquotas do dctfweb_service: patronal 20% + RAT 3% + terceiros 5,8%.
INSS_PATRONAL_RAT_TERCEIROS = 0.288


def _status_linha(nosso, portte, tol: float = TOL):
    """Retorna (diff, bate). Se qualquer lado ausente → não bate."""
    if nosso is None or portte is None:
        return (0.0, False)
    diff = round(float(nosso) - float(portte), 2)
    return (diff, abs(diff) <= tol)


def _inss_total(inss_segurado, inss_base):
    """INSS total (DARF) = segurado + 28,8% da base. None se sem base real."""
    if inss_base is None or float(inss_base) <= 0:
        return None
    return round(float(inss_segurado or 0) + float(inss_base) * INSS_PATRONAL_RAT_TERCEIROS, 2)
