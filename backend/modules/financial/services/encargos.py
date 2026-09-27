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

# Simples ANEXO III — a CPP patronal está DENTRO do DAS (tributação substituída).
# Encargo = LR (0,6124) − CPP 20% − terceiros 5,8% − RAT 3% = 0,3244:
# FGTS 8% + provisões (férias 11,11% + 13º 8,33% + rescisão ~5%).
ENCARGOS_SIMPLES_ANEXO_III = 0.3244

# Simples ANEXO IV — a CPP patronal e o RAT ficam FORA do DAS e são pagos à parte
# (LC 123, art. 18 §5º-C). Terceiros (5,8%) NÃO é devido no Simples.
# Encargo = Anexo III (0,3244) + CPP 20% + RAT 3% = 0,5544.
ENCARGOS_SIMPLES_ANEXO_IV = 0.5544

# ⚠️ A PREMISSA QUE A GUIA DESMENTE — medido em 26/09/2026.
#
# O valor do Anexo III acima foi adotado sobre uma afirmação: "CONFIRMADO Portte
# (Jordan, 20/07): NÃO há cobrança dos 20% patronal". As guias do DAS da Patrimonial
# dizem o contrário — 07/2026 traz INSS de R$ 171,06 (1,0% do documento) e 08/2026
# NENHUMA linha de INSS. No Anexo III a CPP seria ~43% da guia. É Anexo IV.
#
# A diferença são 23 pontos de folha: sobre R$ 106.577,20 (folha de 08/2026), são
# R$ 24.512,76/mês — que é, ao centavo, a CPP patronal medida na guia. A precificação
# não conhece o tributo que a declaração também não conhece.
#
# O número final depende do parecer do tributarista (decisão D1 do plano de
# 26/09/2026). O que NÃO depende, e entra já, é a recusa a responder sem saber o anexo.

# Retrocompat: nomes antigos.
ENCARGOS_SIMPLES_ANEXO_III_ESTIMADO = ENCARGOS_SIMPLES_ANEXO_III
PENDENTE_PORTTE = False

_POR_ANEXO = {
    "III": ENCARGOS_SIMPLES_ANEXO_III,
    "IV": ENCARGOS_SIMPLES_ANEXO_IV,
}


class AnexoNaoDeterminadoError(ValueError):
    """Simples Nacional sem anexo conhecido — e o anexo vale 23 pontos de folha.

    Levantar é a correção do defeito de origem: `encargo_pct("simples_nacional")`
    devolvia 0,3244 SEM SABER o anexo, e precificou os contratos da Patrimonial por
    meses como se a CPP patronal não existisse. Número não sabido é pergunta ao
    contador, não default.
    """


def encargo_pct(regime: str | None, anexo: str | None = None) -> float:
    """Percentual de encargo de folha para o custo de posto.

    `anexo` é OBRIGATÓRIO quando o regime é Simples Nacional: III e IV diferem em 23
    pontos percentuais, e escolher em silêncio é o defeito que este módulo existe para
    não repetir.
    """
    r = (regime or "").lower()
    if r != "simples_nacional":
        return ENCARGOS_LUCRO_REAL
    chave = (anexo or "").strip().upper().replace("ANEXO", "").strip()
    if chave in _POR_ANEXO:
        return _POR_ANEXO[chave]
    raise AnexoNaoDeterminadoError(
        f"Simples Nacional sem anexo determinado (recebi {anexo!r}). "
        f"Anexo III = {ENCARGOS_SIMPLES_ANEXO_III:.2%} de encargo; "
        f"Anexo IV = {ENCARGOS_SIMPLES_ANEXO_IV:.2%} — 23 pontos de diferença. "
        "Preencha `empresas.anexo_simples` ou passe o anexo explicitamente."
    )


def encargo_pct_da_empresa(empresa_id: str) -> float:
    """Encargo de folha DESTA empresa, lendo regime e anexo do cadastro.

    Prefira esta a `encargo_pct` com string literal: os controllers passavam
    `"simples_nacional"` escrito à mão, o que amarra a precificação a uma empresa que
    ninguém declarou.
    """
    import os  # noqa: PLC0415
    import re  # noqa: PLC0415

    import psycopg2  # noqa: PLC0415

    url = re.sub(r"\+asyncpg|\+psycopg2?", "", os.getenv("DATABASE_URL", ""))
    with psycopg2.connect(url) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT regime_tributario, anexo_simples FROM empresas WHERE id = %s",
            (empresa_id,),
        )
        linha = cur.fetchone()
    if not linha:
        raise AnexoNaoDeterminadoError(f"empresa {empresa_id} não existe no cadastro")
    return encargo_pct(linha[0], linha[1])


# Compatibilidade: constante legada (Lucro Real) que os controllers importavam
ENCARGOS_PCT = ENCARGOS_LUCRO_REAL
