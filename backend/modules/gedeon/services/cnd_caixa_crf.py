"""GEDEON — Emissão do CRF/FGTS (Caixa). MESMA interface da SEFAZ-AM.

⚠️ MECANISMO = ROBÔ DE NAVEGADOR (Playwright no HOST), NÃO httpx:
o portal consulta-crf.caixa.gov.br está atrás de WAF (Azion) que devolve 403 a requisições
que não sejam navegador real. Um browser de verdade passa naturalmente; httpx não.
Fluxo: informar CNPJ + UF → "código de verificação" (captcha) → Consultar → CRF (PDF/print jsf).

URL base: https://consulta-crf.caixa.gov.br/consultacrf/
Validade do CRF: 30 dias. Resultado: regular (CRF emitido) ou irregular (com pendências FGTS).

STATUS: encaminhado (interface + estrutura). Fluxo/seletores finalizados no teste ao vivo
(com o solver ativo) — mesma abordagem do robô de ponto.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

PORTAL = "Caixa (CRF/FGTS)"
URL_BASE = "https://consulta-crf.caixa.gov.br/consultacrf/"
UF_EMPRESA = "AM"  # Amazonas


def emitir_crf_caixa(cnpj: str) -> dict:
    """Interface idêntica à SEFAZ-AM. Implementação browser-robot a finalizar ao vivo."""
    # TODO (teste ao vivo): Playwright host (passa o WAF Azion) → preencher CNPJ+UF →
    #   resolver captcha → Consultar → abrir impressao.jsf → baixar PDF → classificar regular/irregular.
    return {
        "portal": PORTAL,
        "cnpj": cnpj,
        "ok": False,
        "regular": None,
        "situacao": None,
        "pdf": None,
        "mensagem": "Emissor browser-robot encaminhado; finalizar no teste ao vivo (WAF Azion + captcha).",
    }
