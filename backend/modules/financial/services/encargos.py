"""Encargos trabalhistas por REGIME/EMPRESA — ponto único (Multi-CNPJ E3).

Antes: ENCARGOS_PCT = 0.6124 duplicado em precificacao_controller e
custeio_controller (premissa Lucro Real: INSS 20% + terceiros 5,8% + RAT 3% +
provisões). No SIMPLES ANEXO III o CPP (20%) está DENTRO do DAS e não há
terceiros → o encargo de folha é bem menor (FGTS 8% + provisões).

DECISÃO (Jordan/Portte, 20/07): estrutura pronta e parametrizável, mas o
NÚMERO do Anexo III só entra quando a Portte passar o percentual EXATO do
custo de posto. Até lá, `PENDENTE_PORTTE=True` e o valor cai no default de
Lucro Real (NENHUMA mudança numérica — evita precificar errado por chute).
"""

import logging

logger = logging.getLogger(__name__)

# Lucro Real (Eletrônica) — em uso, confirmado
ENCARGOS_LUCRO_REAL = 0.6124  # INSS 20 + FGTS 8 + RAT 3 + terceiros 5,8 + férias 11,11 + 13º 8,33 + rescisão 5

# Simples Anexo III (Patrimonial) — CONFIRMADO Portte (Jordan, 20/07): NÃO há
# cobrança dos 20% patronal (CPP fica DENTRO do DAS, junto com terceiros e RAT).
# Encargo de folha = LR (0,6124) − CPP 20% − terceiros 5,8% − RAT 3% = 0,3244,
# ou seja FGTS 8% + provisões (férias 11,11% + 13º 8,33% + rescisão ~5%).
ENCARGOS_SIMPLES_ANEXO_III = 0.3244
# Retrocompat: nome antigo apontando para o valor confirmado.
ENCARGOS_SIMPLES_ANEXO_III_ESTIMADO = ENCARGOS_SIMPLES_ANEXO_III
PENDENTE_PORTTE = False  # Portte confirmou a estrutura (sem 20% patronal) — LIGADO


def encargo_pct(regime: str | None) -> float:
    """Percentual de encargo de folha para o custo de posto, por regime.

    Enquanto PENDENTE_PORTTE, o Simples cai no valor de Lucro Real (default
    seguro) para não precificar com número não-confirmado.
    """
    r = (regime or "").lower()
    if r == "simples_nacional":
        if PENDENTE_PORTTE:
            logger.debug("encargo Simples ainda pendente Portte — usando default LR")
            return ENCARGOS_LUCRO_REAL
        return ENCARGOS_SIMPLES_ANEXO_III
    return ENCARGOS_LUCRO_REAL


# Compatibilidade: constante legada (Lucro Real) que os controllers importavam
ENCARGOS_PCT = ENCARGOS_LUCRO_REAL
