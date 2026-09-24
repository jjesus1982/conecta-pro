"""DGX AA4 — a parametrização fiscal da NFS-e em DADO, não em `if`.

Por que existe
--------------
Até 24/09/2026 o emissor de NFS-e chutava três números e um deles estava errado em
três quartos das notas:

  · **série da DPS** — `_build_dps_xml` tinha `serie_pad = "00900"` chumbado e o XML
    dizia `<serie>900</serie>`. Os DANFSe que o dono subiu mostram a série que as
    duas empresas de fato usam no fisco: **70000**, nas nove notas conferidas;
  · **`cNBS`** — `<cNBS>120032900</cNBS>` chumbado em TODA nota. É o NBS de
    `14.06.01` (instalação/montagem) e ia junto nas notas de vigilância, limpeza e
    manutenção. A Z7 removeu a tag por não ter fonte (§4.4 do relatório dela). Agora
    há fonte: cada código de serviço traz o seu, lido do DANFSe correspondente;
  · **alíquota de ISS** — a Patrimonial é do Simples Nacional e o fisco não devolve
    ISS nenhum para ela (o ISSQN vai no DAS). A coluna fica **NULL**, nunca 0%.

A fonte de cada linha está na coluna `fonte`, com o número da nota de onde saiu. O
que não tem fonte é declarado `'sem fonte'` e NÃO é usado para montar nota nenhuma.

O que esta camada NÃO decide
----------------------------
  · não escolhe o número da nota (isso é `nfse_emissao.proximo_numero`);
  · não calcula imposto: guarda a alíquota que o fisco aplicou e devolveu. Quem
    calcula retenção de INSS é `nfse_lote`, e mesmo lá o número é **proposto** ao
    dono, que confere e transmite;
  · não inventa NBS para código de serviço que não esteja nos DANFSe medidos — pedir
    um código desconhecido devolve `None` e a nota sai sem a tag, como já saía.
"""

from __future__ import annotations

import re
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import text as sqltext
from sqlalchemy.ext.asyncio import AsyncSession

#: Série da DPS medida nos 9 DANFSe de 08–09/2026 das DUAS empresas. Ver `_SEED_EMPRESA`.
SERIE_DPS_MEDIDA = "70000"

_DDL = (
    # Parâmetro por CNPJ emitente. Chave é o CNPJ e não o slug: o slug é rótulo da casa,
    # o CNPJ é o que o fisco conhece.
    "CREATE TABLE IF NOT EXISTS nfse_parametros_empresa ("
    " prestador_cnpj varchar(14) PRIMARY KEY,"
    " serie_dps varchar(5) NOT NULL,"
    " regime varchar(24) NOT NULL,"
    " iss_aliquota numeric(7,4),"  # NULL = Simples Nacional: o fisco não devolve ISS
    " iss_observacao text,"
    " banco_nome varchar(60), banco_codigo varchar(5), agencia varchar(10), conta varchar(20),"
    " pix_chave varchar(60),"
    " fonte text NOT NULL,"
    " updated_at timestamp NOT NULL DEFAULT now())",
    # Código de serviço → NBS. Um NBS por código; nunca o mesmo NBS em dois códigos.
    "CREATE TABLE IF NOT EXISTS nfse_servico_nbs ("
    " codigo_servico varchar(8) PRIMARY KEY,"
    " codigo_formatado varchar(10) NOT NULL,"
    " nbs varchar(16),"
    " descricao_oficial text NOT NULL,"
    " rotulo text NOT NULL,"
    " fonte text NOT NULL,"
    " updated_at timestamp NOT NULL DEFAULT now())",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_nfse_servico_nbs_valor ON nfse_servico_nbs (nbs) WHERE nbs IS NOT NULL",
    # ── Tributos da transição de 2026 e as retenções federais ────────────────────────
    # Cada coluna nasceu de uma nota do fisco; a fonte está em `fonte` e em `_SEED_EMPRESA`.
    "ALTER TABLE nfse_parametros_empresa ADD COLUMN IF NOT EXISTS ibs_uf_aliquota numeric(7,4)",
    "ALTER TABLE nfse_parametros_empresa ADD COLUMN IF NOT EXISTS ibs_mun_aliquota numeric(7,4)",
    "ALTER TABLE nfse_parametros_empresa ADD COLUMN IF NOT EXISTS cbs_aliquota numeric(7,4)",
    "ALTER TABLE nfse_parametros_empresa ADD COLUMN IF NOT EXISTS cst_ibs_cbs varchar(4)",
    "ALTER TABLE nfse_parametros_empresa ADD COLUMN IF NOT EXISTS cclass_trib varchar(8)",
    "ALTER TABLE nfse_parametros_empresa ADD COLUMN IF NOT EXISTS retem_pis_cofins boolean",
    "ALTER TABLE nfse_parametros_empresa ADD COLUMN IF NOT EXISTS codigo_retencao_federal varchar(2)",
    "ALTER TABLE nfse_parametros_empresa ADD COLUMN IF NOT EXISTS retencao_federal_rotulo text",
    "ALTER TABLE nfse_parametros_empresa ADD COLUMN IF NOT EXISTS csll_aliquota numeric(7,4)",
    "ALTER TABLE nfse_parametros_empresa ADD COLUMN IF NOT EXISTS inss_aliquota numeric(7,4)",
    "ALTER TABLE nfse_parametros_empresa ADD COLUMN IF NOT EXISTS irrf_aliquota numeric(7,4)",
    # A chave humana do IRRF. Desligada por decisão do dono em 24/09/2026 — e desligada em
    # DADO, não em `if`: o cálculo continua inteiro e o dia em que o contador disser o
    # contrário é um UPDATE nesta coluna, sem tocar em código e sem deploy.
    "ALTER TABLE nfse_parametros_empresa ADD COLUMN IF NOT EXISTS irrf_reter boolean NOT NULL DEFAULT false",
    "ALTER TABLE nfse_parametros_empresa ADD COLUMN IF NOT EXISTS irrf_observacao text",
)

#: Uma linha por CNPJ. Cada valor vem de um documento do fisco, citado em `fonte`.
#: Dados bancários vêm do corpo da descrição das notas e do cronograma do dono.
_SEED_EMPRESA: tuple[dict[str, Any], ...] = (
    {
        "prestador_cnpj": "35710481000103",
        "serie_dps": SERIE_DPS_MEDIDA,
        "regime": "lucro_real",
        "iss_aliquota": 5.0,
        "iss_observacao": "ISS 5% aplicado e devolvido pelo fisco (pAliqAplic) nas 4 notas conferidas.",
        "banco_nome": "BANCO INTER",
        "banco_codigo": "077",
        "agencia": "0001",
        "conta": "37099007-2",
        "pix_chave": "35710481000103",
        # Transição de 2026 (IBS/CBS). Medido nas 4 notas: IBS-UF 0,10% · IBS-Mun 0,00% · CBS 0,90%.
        "ibs_uf_aliquota": 0.10,
        "ibs_mun_aliquota": 0.00,
        "cbs_aliquota": 0.90,
        "cst_ibs_cbs": "000",
        "cclass_trib": "000001",
        # «8 - PIS/COFINS Não Retidos, CSLL Retido». A dispensa de PIS/COFINS é DECISÃO
        # JUDICIAL citada na própria nota 121: processo nº 1038495-94.2024.4.01.3200.
        # Reter aqui é pagar o que a Justiça já dispensou.
        "retem_pis_cofins": False,
        "codigo_retencao_federal": "8",
        "retencao_federal_rotulo": "8 - PIS/COFINS Não Retidos, CSLL Retido",
        "csll_aliquota": 1.00,
        # Eletrônica não teve retenção previdenciária em nenhuma das 4 notas conferidas
        # («Contribuição Previdenciária - Retida: —»). Ver §7 do relatório: o cronograma
        # do dono manda reter 11% numa nota da Eletrônica e o fisco não reteve em nenhuma.
        "inss_aliquota": None,
        # A ALÍQUOTA tem fonte: NFS-e 121, R$ 18,00 sobre R$ 1.800,00 = 1,00%. O que NÃO
        # tinha fonte era se retém — a 121 reteve e as três de agosto, com o MESMO código
        # 14.01.01 e o mesmo tipo de tomador, não. Uma das duas práticas estava errada.
        # O dono escolheu a de agosto em 24/09/2026: «vamos usar daqui pra frente sem a
        # retenção do irrf». Fica a alíquota, desligada — reverter é um UPDATE.
        "irrf_aliquota": 1.00,
        "irrf_reter": False,
        "irrf_observacao": (
            "DESLIGADO por decisão de Jordan Jesus em 24/09/2026: «vamos usar daqui pra frente sem a "
            "retenção do irrf». Vale daqui para a frente — a NFS-e 121 (17/09/2026) já saiu com "
            "R$ 18,00 de IRRF e fica como está. A alíquota de 1,00% é a que o fisco aplicou nessa "
            "mesma nota; as NFS-e 116, 119 e 120 (08/2026) saíram sem IRRF. Se o contador reverter, "
            "basta UPDATE nfse_parametros_empresa SET irrf_reter = true."
        ),
        "fonte": (
            "DANFSe nº 116, 119, 120 (08/2026) e 121 (09/2026) da CONECTAMAIS ELETRONICA — "
            "série 70000, ISS 5,00%, «Não optante» do Simples. Dados bancários: corpo da "
            "descrição das mesmas notas e do cronograma de emissão de 09/2026."
        ),
    },
    {
        "prestador_cnpj": "66014833000110",
        "serie_dps": SERIE_DPS_MEDIDA,
        "regime": "simples_nacional",
        # NULL de propósito: nas 5 notas conferidas o bloco de ISSQN vem inteiro em branco
        # («BC ISSQN —, Alíquota Aplicada —, ISSQN Apurado —»). Escrever 0,00% aqui seria
        # inventar isenção; o ISSQN dela é apurado dentro do DAS.
        "iss_aliquota": None,
        "iss_observacao": (
            "Simples Nacional: o fisco NÃO devolve ISS nesta empresa — BC, alíquota e ISSQN "
            "apurado vêm vazios no DANFSe. O ISSQN é apurado no DAS. Nunca preencher 0%."
        ),
        "banco_nome": "BANCO CORA SCD",
        "banco_codigo": "403",
        "agencia": "0001",
        "conta": "7382527-7",
        "pix_chave": "66014833000110",
        "ibs_uf_aliquota": 0.10,
        "ibs_mun_aliquota": 0.00,
        "cbs_aliquota": 0.90,
        "cst_ibs_cbs": "000",
        "cclass_trib": "000001",
        # «0 - PIS/COFINS/CSLL Não Retidos» — é o Simples Nacional. Nenhuma CSLL nas 5 notas.
        "retem_pis_cofins": False,
        "codigo_retencao_federal": "0",
        "retencao_federal_rotulo": "0 - PIS/COFINS/CSLL Não Retidos",
        "csll_aliquota": None,
        # A única retenção da Patrimonial: INSS 11%, Art. 31 da Lei 9.711/98, base = bruto
        # menos VA e VT do mês. Conferido nas 5 notas de 08/2026.
        "inss_aliquota": 11.00,
        # Nenhuma das 5 notas da Patrimonial traz IRRF e ela é do Simples: não há alíquota
        # com fonte aqui. A chave existe e está desligada, pela mesma decisão de 24/09/2026.
        "irrf_aliquota": None,
        "irrf_reter": False,
        "irrf_observacao": (
            "DESLIGADO por decisão de Jordan Jesus em 24/09/2026. Além disso não há alíquota com "
            "fonte nesta empresa: nenhuma das 5 NFS-e conferidas traz IRRF e ela é do Simples "
            "Nacional. Ligar `irrf_reter` aqui sem uma alíquota não faz IRRF nenhum aparecer."
        ),
        "fonte": (
            "DANFSe nº 27, 28, 29, 30, 31 (08/2026) da CONECTAMAIS PATRIMONIAL — série 70000, "
            "«Optante - ME/EPP», bloco de ISSQN vazio. Dados bancários: corpo da descrição das "
            "mesmas notas e do cronograma de emissão de 09/2026."
        ),
    },
)

#: Código de tributação nacional (LC 116) → NBS. UM NBS por código, cada um lido do
#: DANFSe onde aquele código aparece. O `cNBS` que estava chumbado no emissor era
#: 1.2003.29.00 — certo só para 14.06.01 e errado nos outros três.
_SEED_NBS: tuple[dict[str, str | None], ...] = (
    {
        "codigo_servico": "110201",
        "codigo_formatado": "11.02.01",
        "nbs": "1.1802.90.00",
        "descricao_oficial": "Vigilância, segurança ou monitoramento de bens, pessoas e semoventes.",
        "rotulo": "Agentes de portaria / vigilância",
        "fonte": "DANFSe nº 28, 29 e 30 (08/2026) da CONECTAMAIS PATRIMONIAL.",
    },
    {
        "codigo_servico": "071002",
        "codigo_formatado": "07.10.02",
        "nbs": "1.1803.10.00",
        "descricao_oficial": "Limpeza, manutenção e conservação de imóveis, chaminés, piscinas e congêneres.",
        "rotulo": "Limpeza, conservação e serviços gerais",
        "fonte": "DANFSe nº 27 e 31 (08/2026) da CONECTAMAIS PATRIMONIAL.",
    },
    {
        "codigo_servico": "140101",
        "codigo_formatado": "14.01.01",
        "nbs": "1.2001.89.00",
        "descricao_oficial": (
            "Lubrificação, limpeza, lustração, revisão, carga e recarga, conserto, restauração, "
            "blindagem, manutenção e conservação de máquinas, veículos, aparelhos, equipamentos, "
            "motores, elevadores ou de qualquer objeto."
        ),
        "rotulo": "Manutenção (CFTV / cerca / portão / cancela)",
        "fonte": "DANFSe nº 116 (08/2026) e 121 (09/2026) da CONECTAMAIS ELETRONICA.",
    },
    {
        "codigo_servico": "140601",
        "codigo_formatado": "14.06.01",
        "nbs": "1.2003.29.00",
        "descricao_oficial": (
            "Instalação e montagem de aparelhos, máquinas e equipamentos, inclusive montagem "
            "industrial, prestados ao usuário final, exclusivamente com material por ele fornecido."
        ),
        "rotulo": "Instalação / portaria remota",
        "fonte": "DANFSe nº 119 e 120 (08/2026) da CONECTAMAIS ELETRONICA.",
    },
)


#: `_ensure` roda o DDL UMA vez por processo E só quando falta alguma coisa.
#:
#: Medido em 24/09/2026 no sandbox: `ALTER TABLE … ADD COLUMN IF NOT EXISTS` pede
#: **AccessExclusiveLock mesmo quando a coluna já existe** — ele não é de graça. Dois
#: processos fazendo isso em tabelas diferentes, em ordens que se cruzam, deram
#: `DeadlockDetectedError`; e uma sessão `idle in transaction` de outro agente segurou a
#: fila por 11 minutos. Com 8 workers de celery subindo juntos depois de um deploy, isso
#: não é hipótese.
#:
#: Então: primeiro uma pergunta barata ao catálogo (`to_regclass` + `information_schema`,
#: que não pegam lock nenhum). Se o DDL já está aplicado, ele **não é pedido**. A flag de
#: processo evita repetir até a pergunta. Nada disso substitui a idempotência do SQL — ela
#: continua lá para quando o DDL de fato precisar rodar.
_ddl_aplicado = False

#: `lock_timeout` para o ALTER não ficar pendurado atrás de transação alheia: falhar em 5s
#: e tentar de novo no próximo acesso é melhor que travar uma tela.
_LOCK_TIMEOUT = "SET LOCAL lock_timeout = '5s'"


async def _ensure(db: AsyncSession) -> None:
    global _ddl_aplicado
    if _ddl_aplicado:
        return
    if (
        await db.execute(
            sqltext(
                "SELECT to_regclass('public.nfse_servico_nbs') IS NOT NULL AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'nfse_parametros_empresa' AND column_name = 'irrf_reter')"
            )
        )
    ).scalar():
        _ddl_aplicado = True
    else:
        await db.execute(sqltext(_LOCK_TIMEOUT))
        for sql in _DDL:
            await db.execute(sqltext(sql))
    # ON CONFLICT DO NOTHING: rodar de novo NÃO desfaz um ajuste que o dono fizer na linha.
    for e in _SEED_EMPRESA:
        await db.execute(
            sqltext(
                "INSERT INTO nfse_parametros_empresa"
                " (prestador_cnpj, serie_dps, regime, iss_aliquota, iss_observacao,"
                "  banco_nome, banco_codigo, agencia, conta, pix_chave, fonte,"
                "  ibs_uf_aliquota, ibs_mun_aliquota, cbs_aliquota, cst_ibs_cbs, cclass_trib,"
                "  retem_pis_cofins, codigo_retencao_federal, retencao_federal_rotulo,"
                "  csll_aliquota, inss_aliquota, irrf_aliquota, irrf_reter, irrf_observacao)"
                " VALUES (:prestador_cnpj, :serie_dps, :regime, :iss_aliquota, :iss_observacao,"
                "  :banco_nome, :banco_codigo, :agencia, :conta, :pix_chave, :fonte,"
                "  :ibs_uf_aliquota, :ibs_mun_aliquota, :cbs_aliquota, :cst_ibs_cbs, :cclass_trib,"
                "  :retem_pis_cofins, :codigo_retencao_federal, :retencao_federal_rotulo,"
                "  :csll_aliquota, :inss_aliquota, :irrf_aliquota, :irrf_reter, :irrf_observacao)"
                " ON CONFLICT (prestador_cnpj) DO NOTHING"
            ),
            e,
        )
    for s in _SEED_NBS:
        await db.execute(
            sqltext(
                "INSERT INTO nfse_servico_nbs"
                " (codigo_servico, codigo_formatado, nbs, descricao_oficial, rotulo, fonte)"
                " VALUES (:codigo_servico, :codigo_formatado, :nbs, :descricao_oficial, :rotulo, :fonte)"
                " ON CONFLICT (codigo_servico) DO NOTHING"
            ),
            s,
        )
    _ddl_aplicado = True
    await db.commit()


def so_digitos(v: Any) -> str:
    return re.sub(r"\D", "", str(v or ""))


async def parametros_de(db: AsyncSession, cnpj: str) -> dict[str, Any] | None:
    """Parâmetros do CNPJ emitente. `None` = empresa sem parametrização — não emite."""
    linha = (
        (
            await db.execute(
                sqltext("SELECT * FROM nfse_parametros_empresa WHERE prestador_cnpj = :c"),
                {"c": so_digitos(cnpj)},
            )
        )
        .mappings()
        .first()
    )
    return dict(linha) if linha else None


async def serie_de(db: AsyncSession, cnpj: str) -> str:
    """Série da DPS do CNPJ. Sem linha, devolve a série medida — nunca um chute novo."""
    p = await parametros_de(db, cnpj)
    return str(p["serie_dps"]) if p else SERIE_DPS_MEDIDA


async def nbs_de(db: AsyncSession, codigo_servico: str) -> str | None:
    """NBS do código de serviço. Código desconhecido devolve None — e a tag não vai.

    É de propósito que não há fallback: um NBS aplicado ao código errado foi exatamente
    o defeito que o fisco devolveu com descrição trocada nas notas de vigilância.
    """
    cod = so_digitos(codigo_servico)[:6]
    linha = (
        await db.execute(sqltext("SELECT nbs FROM nfse_servico_nbs WHERE codigo_servico = :c"), {"c": cod})
    ).first()
    return (linha[0] or None) if linha else None


async def iss_aliquota_de(db: AsyncSession, cnpj: str) -> float | None:
    """Alíquota de ISS da empresa, ou `None` quando o fisco não devolve ISS (Simples).

    `None` NÃO é zero. Quem grava a nota tem de deixar a coluna nula — ver Z7 §3.
    """
    p = await parametros_de(db, cnpj)
    if not p:
        return None
    v = p.get("iss_aliquota")
    return float(v) if v is not None else None


async def servicos(db: AsyncSession) -> list[dict[str, Any]]:
    """Catálogo de códigos de serviço com NBS e fonte, para a tela e para o oráculo."""
    linhas = (
        (
            await db.execute(
                sqltext(
                    "SELECT codigo_servico, codigo_formatado, nbs, descricao_oficial, rotulo, fonte"
                    " FROM nfse_servico_nbs ORDER BY codigo_formatado"
                )
            )
        )
        .mappings()
        .all()
    )
    return [dict(x) for x in linhas]


# ---------------------------------------------------------------------------
# O caminho do dinheiro: os tributos da nota, com a regra que as notas reais mostram
# ---------------------------------------------------------------------------

#: «faça de tudo para ao emitir não pagarmos imposto indevidamente» — Jordan Jesus,
#: 24/09/2026. Cada linha abaixo é uma regra lida em documento que o fisco emitiu.
_CENTAVO = Decimal("0.01")


def _q(v: Decimal) -> Decimal:
    return v.quantize(_CENTAVO, rounding=ROUND_HALF_UP)


def calcular_tributos(
    valor_servico: Decimal | float | str,
    par: dict[str, Any],
    *,
    deducao_inss: Decimal | float | str | None = None,
    iss_retido_pelo_tomador: bool = False,
) -> dict[str, Any]:
    """Os tributos de UMA NFS-e, a partir dos parâmetros medidos do CNPJ emitente.

    Função pura: sem banco, sem rede. O oráculo importa ESTA e a recalcula contra as
    nove notas que o fisco emitiu em 08–09/2026.

    As regras, cada uma com a nota onde foi medida
    ----------------------------------------------
    **ISS.** `iss_aliquota` nula = o fisco não devolve ISS nesta empresa (Simples
    Nacional: o ISSQN vai no DAS). Fica `None`, **nunca 0,00** — zero afirmaria isenção.
    Medido nas 5 notas da Patrimonial, onde BC, alíquota e ISSQN vêm todos «-».

    **Base do IBS/CBS = valor MENOS o ISS da nota.** Nas 4 notas da Eletrônica, o campo
    «Exclusões e Reduções da Base de Cálculo» é *exatamente* o ISSQN apurado (190 sobre
    3.800, 300 sobre 6.000, 100 sobre 2.000, 90 sobre 1.800). Cobrar IBS/CBS sobre o
    valor cheio **pagaria a mais**. Na Patrimonial não há ISS na nota, logo a exclusão é
    zero e a base é o valor cheio — é a MESMA regra, não uma exceção.

    **PIS e COFINS não são retidos.** Na Eletrônica por **decisão judicial** citada na
    própria NFS-e 121 (processo nº 1038495-94.2024.4.01.3200), código «8 - PIS/COFINS
    Não Retidos, CSLL Retido»; na Patrimonial por ser Simples, código «0». Reter seria
    pagar o que a Justiça dispensou.

    **CSLL 1%** em todas as 4 notas da Eletrônica (38/60/20/18). **Nenhuma** nas 5 da
    Patrimonial.

    **INSS 11%**, Art. 31 da Lei 9.711/98, base = bruto **menos** vale-alimentação e
    vale-transporte do mês. Só na Patrimonial (cessão de mão de obra).

    **IRRF: calculado sempre, DESLIGADO por parâmetro.** A alíquota de 1% tem fonte (NFS-e
    121: R$ 18,00 sobre R$ 1.800,00); o que não tinha era se retém — a 121 reteve e as três
    de agosto, mesmo código e mesmo tipo de tomador, não. Jordan Jesus decidiu em 24/09/2026:
    «vamos usar daqui pra frente sem a retenção do irrf». Vale daqui para a frente; a 121
    fica como saiu. A chave é `irrf_reter`, uma coluna — ligar de volta não mexe em código.

    O centavo do INSS
    -----------------
    `vRetCP` é **digitado** na DPS, não calculado pelo órgão — e as notas provam: de cinco
    retenções da Patrimonial, quatro batem com truncamento (1.326,76 · 3.689,21 · 918,13 ·
    3.156,37) e uma com arredondamento (2.815,20 sobre 25.592,71, que truncado daria
    2.815,19). Por isso vêm os dois valores, e quem decide é quem assina.
    """
    valor = Decimal(str(valor_servico))
    aliq_iss = par.get("iss_aliquota")
    iss = _q(valor * Decimal(str(aliq_iss)) / 100) if aliq_iss is not None else None

    base_ibs_cbs = valor - (iss or Decimal(0))
    pct = lambda k: Decimal(str(par.get(k) or 0)) / 100  # noqa: E731
    ibs_uf = _q(base_ibs_cbs * pct("ibs_uf_aliquota"))
    ibs_mun = _q(base_ibs_cbs * pct("ibs_mun_aliquota"))
    cbs = _q(base_ibs_cbs * pct("cbs_aliquota"))

    csll = _q(valor * pct("csll_aliquota")) if par.get("csll_aliquota") is not None else None

    inss = inss_truncado = base_inss = None
    if par.get("inss_aliquota") is not None:
        base_inss = valor - Decimal(str(deducao_inss or 0))
        bruto_inss = base_inss * pct("inss_aliquota")
        inss = _q(bruto_inss)
        inss_truncado = bruto_inss.quantize(_CENTAVO, rounding=ROUND_DOWN)

    # IRRF: o cálculo existe SEMPRE; quem decide se ele sai é a chave `irrf_reter`, que é
    # dado. Desligada em 24/09/2026 por decisão do dono. Ligar de volta é um UPDATE numa
    # coluna — nenhuma linha de código muda, nenhum deploy é preciso.
    irrf = None
    if par.get("irrf_reter") and par.get("irrf_aliquota") is not None:
        irrf = _q(valor * pct("irrf_aliquota"))

    retencoes = (csll or Decimal(0)) + (inss or Decimal(0)) + (irrf or Decimal(0))
    if iss is not None and iss_retido_pelo_tomador:
        # Retido pelo tomador muda o LÍQUIDO, não o devido (NFS-e 120: R$ 120 = ISS 100 + CSLL 20).
        retencoes += iss

    return {
        "valor_servico": float(valor),
        "iss_aliquota": float(aliq_iss) if aliq_iss is not None else None,
        "iss_valor": float(iss) if iss is not None else None,
        "iss_retido_pelo_tomador": bool(iss_retido_pelo_tomador and iss is not None),
        "base_ibs_cbs": float(base_ibs_cbs),
        "exclusoes_base": float(iss or Decimal(0)),
        "ibs_uf": float(ibs_uf),
        "ibs_mun": float(ibs_mun),
        "cbs": float(cbs),
        "total_ibs_cbs": float(_q(ibs_uf + ibs_mun + cbs)),
        "cst_ibs_cbs": par.get("cst_ibs_cbs"),
        "cclass_trib": par.get("cclass_trib"),
        "pis_retido": 0.0,
        "cofins_retido": 0.0,
        "codigo_retencao_federal": par.get("codigo_retencao_federal"),
        "retencao_federal_rotulo": par.get("retencao_federal_rotulo"),
        "csll": float(csll) if csll is not None else None,
        "base_inss": float(base_inss) if base_inss is not None else None,
        "inss": float(inss) if inss is not None else None,
        "inss_truncado": float(inss_truncado) if inss_truncado is not None else None,
        "irrf": float(irrf) if irrf is not None else None,
        "irrf_reter": bool(par.get("irrf_reter")),
        "irrf_aliquota": float(par["irrf_aliquota"]) if par.get("irrf_aliquota") is not None else None,
        "irrf_observacao": par.get("irrf_observacao"),
        "total_retencoes": float(_q(retencoes)),
        "valor_liquido": float(_q(valor - retencoes)),
    }
