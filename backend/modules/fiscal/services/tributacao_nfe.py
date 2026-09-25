"""DGX Z4 — a tributação da NF-e de MERCADORIA das duas empresas da casa (24/09/2026).

**Por que existe.** A nota pode ser aceita pela SEFAZ e ainda assim estar errada em tributo — e
aí o problema aparece meses depois, com multa. Até hoje os dois caminhos de NF-e do sistema
gravam tributo FIXO: `financial/integrations/nfe_provider.py` põe CFOP 5933 + CST 40 + ICMS zero
(é a nota de SERVIÇO, ISSQN) e `fiscal_contabil/notas_fiscais/nfe/controller.py` põe CST 40 +
`vICMSDeson` "0.00" por default. Não existia nenhuma regra de mercadoria. Este módulo é essa
regra — e, onde a norma não está no repositório, ele devolve `None` e diz «sem fonte — decisão do
contador» em vez de inventar alíquota.

**Princípio.** Toda alíquota devolvida carrega `origem_regra` (de onde veio o número) e `norma`
(o dispositivo legal). Nenhum número sai sem os dois. `None` é resposta legítima e preferível.

**O achado que muda tudo.** As duas empresas ficam em MANAUS, dentro da ZFM. O incentivo do
Convênio ICM 65/88 vale para quem vende DE FORA para a ZFM — não para quem já está dentro. Uma
venda da CONECTAMAIS ELETRONICA para outra empresa de Manaus, mesmo com SUFRAMA do destinatário,
é operação INTERNA do Amazonas (CFOP 5101/5102, ICMS 20%), não venda para a ZFM. A inscrição
SUFRAMA 210140500 serve para a empresa RECEBER o incentivo, não para concedê-lo. O ramo 6109/6110
está implementado e testado aqui, mas hoje é inalcançável para os dois CNPJs — e o serviço diz isso
em `bloqueios`, em vez de deixar a tela oferecer um caminho que não existe.

**Correção AA5 (24/09/2026) — o imposto que já foi pago.** Até esta data a régua devolvia CFOP
5102 / CST 00 / ICMS 20% para toda venda interna, inclusive de mercadoria cujo ICMS já tinha sido
retido por substituição tributária na COMPRA — cobrança em duplicidade em quase metade do
catálogo (43 dos 95 produtos de `fin_produtos`). Agora a saída depende de **como a mercadoria
entrou** (`produto["icms_entrada_cst"]`, que vem de `fin_produtos.icms_entrada_cst`): entrou com
ST → CFOP 5405 / CST 060 / ICMS zero; entrou tributada → como antes; **não se sabe → recusa**,
com mensagem que ensina, em vez de chutar. Ver o bloco «COMO A MERCADORIA ENTROU».

**Determinístico e sem I/O externo.** O único acesso a banco é ler a identidade da empresa
(`empresas`, via `empresa_lookup`). Nada de SEFAZ, nada de rede, nada de relógio. `demo()` roda o
autoteste sem banco nenhum: `python3 -m modules.fiscal.services.tributacao_nfe`.

**Medido no nascimento** (sandbox, 24/09/2026): `tax_configurations` = 0 linhas · `suframa_configs`
= 0 linhas · `cfops` = 2 linhas (ambas de serviço, 5933/6933) · `ncms` = 10.515 linhas com
descrição e **zero** alíquota (ipi/pis/cofins/cest/mva todos NULL no banco, apesar do default do
model) · `nfe_entradas` = 84 notas, 51 com XML, **207 itens reais** de fornecedores de Manaus — a
referência de mercado usada aqui. `nfe_compras_estoque` (147 itens) **não** tem CST/CSOSN/CFOP:
só `ncm`. O tributo real do fornecedor só existe dentro de `nfe_entradas.xml_raw`.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

# Reuso: os enums de CST/CSOSN/origem já existem e são a tabela oficial. Não recriar.
from modules.financial.models.tax_configuration import ICMSCSOSN, ICMSCST, ICMSOrigin

# ── UF a partir do código IBGE do município (`empresas` NÃO tem coluna de UF nem de CRT).
# Fonte: tabela de UF do IBGE, a mesma do campo cUF da NF-e (MOC 4.00, Anexo VI).
_UF_POR_IBGE = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR",
    "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}  # fmt: skip

SEM_FONTE = "sem fonte — decisão do contador"

# ── as alíquotas. CADA uma com norma E origem. Nenhuma inventada.
ICMS_INTERNO_AM = Decimal("20.00")
N_ICMS_INTERNO = "RICMS-AM — alíquota interna do Amazonas (dispositivo NÃO localizado no repositório)"
O_ICMS_INTERNO = "medido: 76 itens de NF-e AM→AM com CST 00 em nfe_entradas (2025–2026), todos a 20,00%"

ICMS_INTERESTADUAL = Decimal("12.00")
N_ICMS_INTEREST = "Resolução do Senado Federal nº 22/1989, art. 1º, caput"
O_ICMS_INTEREST = "norma citada; conferido pelo inverso — 1 item RS→AM a 7,00% (art. 1º, parágrafo único)"

ICMS_INTERESTADUAL_IMPORTADO = Decimal("4.00")
N_ICMS_IMPORT = "Resolução do Senado Federal nº 13/2012, art. 1º"
O_ICMS_IMPORT = (
    "Resolução do Senado Federal nº 13/2012 — mercadoria com conteúdo de importação; "
    "nenhum item de origem estrangeira medido no repositório"
)

PIS_NAO_CUMULATIVO = Decimal("1.65")
COFINS_NAO_CUMULATIVO = Decimal("7.60")
N_PIS_COFINS = "Lei 10.637/2002, art. 2º (PIS) e Lei 10.833/2003, art. 2º (COFINS) — não-cumulativo"
O_PIS_COFINS = "norma citada; medido em 39 itens de fornecedores CRT=3 a exatamente 1,65% / 7,60%"

#: origem da mercadoria (campo `orig` da NF-e) que puxa a alíquota de 4% do Senado 13/2012
_ORIGENS_IMPORTADAS = {
    ICMSOrigin.ESTRANGEIRA_IMPORTACAO_DIRETA,  # 1
    ICMSOrigin.ESTRANGEIRA_ADQUIRIDA_MERCADO_INTERNO,  # 2
    ICMSOrigin.NACIONAL_CONTEUDO_IMPORTADO_40_70,  # 3
    ICMSOrigin.NACIONAL_CONTEUDO_IMPORTADO_ACIMA_70,  # 8
}

N_ZFM = "Convênio ICM 65/88, cláusula primeira; Decreto-Lei 288/1967, art. 4º"
N_ZFM_DESON = "MOC NF-e 4.00, grupo N — N27a (vICMSDeson) e N28 (motDesICMS = 7, SUFRAMA)"
N_ZFM_IPI = "Decreto 7.212/2010 (RIPI), art. 84 — isenção de IPI na remessa de produto nacional à ZFM"
N_ZFM_PISCOFINS = "Lei 10.996/2004, art. 2º — alíquota zero de PIS/COFINS na venda destinada à ZFM"

#: PIS/COFINS suspensos por DECISÃO JUDICIAL. O número do processo vem de
#: `empresas.pis_cofins_processo` — parâmetro, não constante: é o que dá a fonte da alíquota
#: zero na própria nota, e o dia em que a liminar cair, cai numa linha de tabela.
#:
#: Decisão do dono em 25/09/2026: *«pis e cofins na nota de material, nós temos a liminar,
#: então não é ser cobrado imposto sobre ela, é pra sair zerado.»* Bate com a medição: a NF-e
#: real 10.026 (17/09, protocolo 113263811849419) traz vPIS 0,00 e vCOFINS 0,00. E a NFS-e 121
#: do mesmo dia escreve na descrição: «NÃO HAVERÁ RETENÇÃO DE PIS E COFINS, CONFORME PROCESSO
#: N° 1038495-94.2024.4.01.3200».
#:
#: O QUE FICA SEM FONTE, e o contador precisa dizer: o **CST**. Liminar SUSPENDE a exigibilidade,
#: e o CST de suspensão é o 09; alíquota zero é o 06. Não tenho o texto da liminar para saber
#: qual dos dois ela sustenta, e a DANFE do dono não mostra o CST de PIS/COFINS por item. Fica
#: 09 (suspensão), que é o que a palavra «liminar» descreve — com a pergunta registrada.
N_PIS_COFINS_LIMINAR = "decisão judicial — processo nº {proc}"
CST_PIS_COFINS_LIMINAR = "09"

N_SIMPLES = "LC 123/2006, art. 18 (recolhimento unificado) e art. 23 (vedação ao crédito)"
N_CSOSN = "Ajuste SINIEF 07/2005, Anexo, Tabela B (CSOSN — incluída pelo Ajuste SINIEF 03/2010)"
N_CRT = "MOC NF-e 4.00, campo B21a (CRT): 1 = Simples Nacional, 3 = Regime Normal"
N_DIFAL = "EC 87/2015; LC 190/2022; Convênio ICMS 236/2021 (partilha ao destino)"
N_CFOP = "Convênio SINIEF s/nº de 15/12/1970, Anexo (tabela de CFOP)"
N_IPI_CONTRIB = "Decreto 7.212/2010 (RIPI), art. 24 — contribuinte do IPI é o industrial ou o equiparado"
N_CST = "MOC NF-e 4.00, grupo N — Tabela A (origem) e Tabela B (CST de ICMS)"
N_ST = "Convênio ICMS 142/2018 (CEST e mercadorias sujeitas a ST)"
N_TIPI = "Decreto 11.158/2022 (TIPI)"

#: o que o repositório tem de ST POR NCM — nada (CEST e MVA vazios). O que ele TEM é o fato por
#: PRODUTO: como aquela mercadoria entrou. Ver o bloco «COMO A MERCADORIA ENTROU», abaixo.
O_ST = (
    "MVA e CEST por NCM: não determináveis — ncms.icms_cest e ncms.icms_st_mva estão vazios nas "
    "10.515 linhas e suframa_configs/tax_configurations têm 0 linhas. " + SEM_FONTE + ". "
    "O que É determinável é outra coisa, e é o que esta régua usa: o CST de ICMS da NF-e de "
    "ENTRADA do produto (ver `icms_entrada_cst`)."
)

# ─────────────────────────── COMO A MERCADORIA ENTROU (AA5, 24/09/2026) ───────────────────────
#
# O defeito que esta parte corrige: até 24/09/2026 a régua devolvia CFOP 5102 / CST 00 / ICMS 20%
# para TODA venda interna — inclusive para mercadoria cujo ICMS já tinha sido retido por
# substituição tributária na COMPRA. Isso é cobrar o imposto duas vezes.
#
# **A régua de fora do sistema:** a NF-e nº 10.026, série 1, da CONECTAMAIS ELETRONICA
# (chave 1326 0935 7104 8100 0103 5500 1000 0100 2618 0548 4852, protocolo 113263811849419,
# autorizada em 17/09/2026, destinatário CONDOMINIO RESIDENCIAL PARQUE DOS FRANCESES, R$ 2.518,00).
# Os SEIS itens dela — NCM 85444900, 85044021, 85365090, 83014000, 85369090 e 39162000 — saíram
# todos com **CFOP 5405 · CST 060 · BC ICMS 0,00 · V.ICMS 0,00 · %ICMS 0,00**, sob a natureza
# «Venda de mercadoria, adquirida ou recebida de terceiros, sujeita a ST».
#
# **A medição de dentro:** 209 itens lidos de `nfe_entradas.xml_raw` (51 XMLs de fornecedores de
# Manaus) em 24/09/2026 — CST de ICMS 60 → 97 · 00 → 73 · 20 → 5 · 50 → 5 · 41 → 4;
# CSOSN 102 → 13 · 500 → 9 · 400 → 1; 2 itens sem grupo de ICMS.
# **106 dos 209 (50,7%) entraram com o ICMS já retido por ST.** O CFOP de entrada desses 106:
# 5929 (cupom) → 61 · 5405 → 44 · 5403 → 1 — ou seja, o próprio fornecedor já vendia como
# contribuinte SUBSTITUÍDO.
#
# **O fato é do PRODUTO, não do NCM.** Medido: dos 147 códigos de produto (`cProd`) das notas de
# entrada, **zero** têm entradas com CST divergente entre si — o fato é estável por produto. Já
# por NCM há **5 códigos** com entradas divergentes (34054000, 40151900, 94032090, 85365090,
# 34052000), então NCM não serve de chave. Por isso o fato mora em `fin_produtos.icms_entrada_cst`
# (serviço `modules/fiscal/services/icms_entrada.py`), preenchido do XML da nota de entrada, e
# chega aqui pelo `produto`, nunca por palpite.

#: CST/CSOSN de ICMS que, na ENTRADA, significam «o ICMS já foi retido por substituição
#: tributária». Tabela B do MOC NF-e 4.00 (CST 10/30/60/70) e do Ajuste SINIEF 07/2005
#: (CSOSN 201/202/203/500).
ICMS_ENTRADA_COM_ST = {"10", "30", "60", "70", "201", "202", "203", "500"}

#: CST/CSOSN de ICMS que, na ENTRADA, significam tributação normal — a saída segue como sempre.
ICMS_ENTRADA_NORMAL = {"00", "101", "102", "103"}

#: a Tabela B do Ajuste SINIEF 07/2005 inteira. Serve para NÃO confundir o CSOSN «400» (3 dígitos
#: de verdade) com o «origem+CST» de 3 dígitos que a DANFE imprime («060» = origem 0 + CST 60).
CSOSN_TODOS = {"101", "102", "103", "201", "202", "203", "300", "400", "500", "900"}

CFOP_ST_INTERNA_REVENDA = "5405"
CST_SAIDA_ST = "60"
CSOSN_SAIDA_ST = "500"

N_CFOP_5405 = (
    "Convênio SINIEF s/nº de 15/12/1970, Anexo — CFOP 5405: venda de mercadoria adquirida ou "
    "recebida de terceiros, em operação com mercadoria sujeita ao regime de substituição "
    "tributária, na condição de contribuinte substituído"
)
N_CST_60 = "MOC NF-e 4.00, grupo N, Tabela B — CST 60: ICMS cobrado anteriormente por substituição tributária"
N_CSOSN_500 = (
    "Ajuste SINIEF 07/2005, Anexo, Tabela B — CSOSN 500: ICMS cobrado anteriormente por "
    "substituição tributária ou por antecipação"
)
O_ENTRADA_ST = (
    "a mercadoria ENTROU com o ICMS já retido por ST (CST/CSOSN da NF-e de entrada do "
    "fornecedor). Provado de fora: NF-e nº 10.026 série 1 da própria empresa, protocolo "
    "113263811849419 (17/09/2026), 6 itens com CFOP 5405 / CST 060 / ICMS 0,00. Medido de "
    "dentro: 106 dos 209 itens de nfe_entradas entraram assim"
)
O_ENTRADA_NORMAL = (
    "a mercadoria ENTROU com ICMS normal (CST 00 / CSOSN 101-103 na NF-e de entrada) — "
    "não houve retenção anterior, a saída é tributada"
)

#: a recusa que ENSINA. Sem saber como a mercadoria entrou, o sistema não escolhe CFOP.
MSG_ENTRADA_DESCONHECIDA = (
    "Não sei como esta mercadoria entrou{qual}. Sem o CST de ICMS da NF-e de ENTRADA não dá para "
    "saber se o ICMS já foi retido por substituição tributária — e aí a saída é CFOP 5405 / "
    "CST 060 com ICMS ZERO, como saiu a nossa própria NF-e nº 10.026 — ou se é tributação normal, "
    "CFOP 5102 / CST 00 a 20%. Metade do que a casa compra entra com ICMS-ST (106 de 209 itens "
    "medidos), então chutar erra quase uma vez em duas. Registre a entrada em Fiscal → Notas "
    "fiscais → «Como a mercadoria entrou (ICMS-ST)», ou importe a NF-e de entrada do fornecedor. "
    "Emitir com o CFOP errado é pior do que não emitir."
)

#: ST fora da venda interna em revenda: existe CFOP (6404), mas o tratamento do ICMS não.
MSG_ST_SEM_FONTE = (
    "A mercadoria entrou com ICMS já retido por ST (CST/CSOSN {cst} na nota de entrada), mas esta "
    "operação — {destino}, {operacao} — não tem tratamento com fonte neste repositório. Só a "
    "venda INTERNA do Amazonas, em revenda, está provada (CFOP 5405 / CST 060 / ICMS zero — NF-e "
    "10.026 série 1). Saída interestadual de mercadoria já substituída envolve ressarcimento ao "
    "estado de origem e CFOP 6404, e nada disso está normado aqui. " + SEM_FONTE
)

N_ENTRADA = (
    "MOC NF-e 4.00, grupo N, Tabela B (CST) e Ajuste SINIEF 07/2005, Anexo, Tabela B (CSOSN) — "
    "lidos do XML da NF-e de ENTRADA do fornecedor"
)


def classificar_entrada(cst: Any) -> str | None:
    """Como a mercadoria entrou, a partir do CST/CSOSN de ICMS da nota de ENTRADA.

    `"st"` = ICMS já retido por substituição tributária · `"normal"` = tributação normal ·
    `None` = não se sabe (inclui CST 20/40/41/50/51/90 e CSOSN 300/400/900, que existem nas
    notas de entrada da casa mas **não têm tratamento de saída com fonte aqui** — 9 dos 95
    produtos de `fin_produtos` caem nesse balde, medido em 24/09/2026).
    """
    c = str(cst or "").strip()
    if not c:
        return None
    # a DANFE imprime origem+CST junto («060»); o XML traz os dois separados («0» e «60»).
    # CSOSN tem 3 dígitos de verdade (500, 102) e por isso é testado ANTES de desmontar.
    if len(c) == 3 and c not in CSOSN_TODOS:
        c = c[1:]
    if c in ICMS_ENTRADA_COM_ST:
        return "st"
    if c in ICMS_ENTRADA_NORMAL:
        return "normal"
    return None


def _d(v: Any) -> Decimal:
    return Decimal(str(v or 0))


def _cent(v: Decimal) -> float:
    return float(v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _uf_da_empresa(empresa: dict) -> str | None:
    return _UF_POR_IBGE.get(str(empresa.get("codigo_municipio_ibge") or "")[:2])


def _digitos(v: Any) -> str:
    return "".join(c for c in str(v or "") if c.isdigit())


def crt_do_regime(regime: str | None) -> str | None:
    """CRT da NF-e a partir de `empresas.regime_tributario` — não existe coluna `crt`."""
    r = (regime or "").strip().lower()
    if r == "simples_nacional":
        return "1"
    if r in ("lucro_real", "lucro_presumido", "lucro_arbitrado"):
        return "3"
    return None


def classificar_destino(uf_emit: str | None, destinatario: dict) -> str:
    """Nomeia a operação. É aqui que mora o achado da ZFM.

    `zfm_entrante` só existe quando o EMITENTE está fora do Amazonas — o incentivo do
    Convênio ICM 65/88 é para quem vende DE FORA para a ZFM. Emitente de Manaus vendendo
    para Manaus faz operação interna, com SUFRAMA do destinatário ou sem.
    """
    uf_dest = (destinatario.get("uf") or "").upper().strip()
    contrib = bool(destinatario.get("contribuinte"))
    tem_suframa = bool(_digitos(destinatario.get("suframa")))
    if tem_suframa and uf_emit and uf_emit != "AM" and uf_dest == "AM":
        return "zfm_entrante"
    if uf_dest and uf_emit and uf_dest == uf_emit:
        return "interna_contribuinte" if contrib else "interna_nao_contribuinte"
    return "interestadual_contribuinte" if contrib else "interestadual_nao_contribuinte"


DESTINOS = {
    "interna_contribuinte": "Venda dentro do Amazonas, a contribuinte",
    "interna_nao_contribuinte": "Venda dentro do Amazonas, a não contribuinte",
    "interestadual_contribuinte": "Venda para outro estado, a contribuinte",
    "interestadual_nao_contribuinte": "Venda para outro estado, a não contribuinte (DIFAL)",
    "zfm_entrante": "Venda para a ZFM com SUFRAMA (emitente FORA do Amazonas)",
}

#: CFOP por (destino, operação). `producao` = saída de produção do próprio estabelecimento.
_CFOP = {
    ("interna_contribuinte", "revenda"): "5102",
    ("interna_contribuinte", "producao"): "5101",
    ("interna_nao_contribuinte", "revenda"): "5102",
    ("interna_nao_contribuinte", "producao"): "5101",
    ("interestadual_contribuinte", "revenda"): "6102",
    ("interestadual_contribuinte", "producao"): "6101",
    ("interestadual_nao_contribuinte", "revenda"): "6108",
    ("interestadual_nao_contribuinte", "producao"): "6107",
    ("zfm_entrante", "revenda"): "6110",
    ("zfm_entrante", "producao"): "6109",
}


def _linha(rotulo: str, valor: Any, norma: str, origem: str) -> dict:
    """Uma linha do cálculo com a norma ao lado — é o que a tela mostra e o oráculo confere."""
    return {"rotulo": rotulo, "valor": valor, "norma": norma, "origem_regra": origem}


def _bloqueios(empresa: dict, destino: str) -> list[str]:
    """O que impede a nota de existir, antes de qualquer alíquota."""
    out: list[str] = []
    nome = empresa.get("nome_fantasia") or empresa.get("razao_social") or empresa.get("cnpj")
    if not (empresa.get("inscricao_estadual") or "").strip():
        out.append(
            f"{nome} não tem Inscrição Estadual cadastrada — sem IE não se emite NF-e modelo 55 de "
            "mercadoria (o documento dela hoje é a NFS-e). Cadastrar a IE ou confirmar com o contador "
            "que a empresa não é contribuinte do ICMS."
        )
    if destino == "zfm_entrante":
        out.append(
            "Ramo 6109/6110 inalcançável para os CNPJs da casa: ambos estão em Manaus, DENTRO da ZFM, "
            "e o incentivo é para quem vende de fora para cá. " + N_ZFM
        )
    return out


def _icms_regime_normal(destino: str, base: Decimal, origem_merc: str, entrada: str | None = None) -> tuple:
    """(cst, aliquota, norma, origem, deson, mensagens) do ICMS no regime normal."""
    if entrada == "st":
        # ICMS já retido por ST na COMPRA. Não se cobra de novo na saída: CST 60, sem alíquota,
        # sem base. É o que a NF-e 10.026 da própria empresa faz nos seis itens.
        return (CST_SAIDA_ST, None, N_CST_60, O_ENTRADA_ST, None, [])
    if destino == "zfm_entrante":
        val = base * ICMS_INTERESTADUAL / 100
        deson = {
            "vICMSDeson": _cent(val),
            "motDesICMS": "7",
            "norma": N_ZFM_DESON,
            "origem_regra": (
                "Convênio ICM 65/88, cláusula primeira, §1º — o ICMS desonerado é abatido do preço; "
                "a alíquota que o quantifica é a interestadual de saída (" + N_ICMS_INTEREST + ")"
            ),
        }
        return (
            ICMSCST.ISENTA_OU_NAO_TRIBUTADA,
            None,
            N_ZFM,
            "norma citada — isenção: não há alíquota a destacar",
            deson,
            [],
        )
    if destino.startswith("interna"):
        return (ICMSCST.TRIBUTADA_INTEGRALMENTE, ICMS_INTERNO_AM, N_ICMS_INTERNO, O_ICMS_INTERNO, None, [])
    importada = str(origem_merc or "0") in _ORIGENS_IMPORTADAS
    aliq = ICMS_INTERESTADUAL_IMPORTADO if importada else ICMS_INTERESTADUAL
    norma = N_ICMS_IMPORT if importada else N_ICMS_INTEREST
    origem = O_ICMS_IMPORT if importada else O_ICMS_INTEREST
    msgs: list[str] = []
    if destino == "interestadual_nao_contribuinte":
        msgs.append(
            f"DIFAL devido ao estado de destino ({N_DIFAL}). A alíquota interna da UF de destino não "
            f"existe no repositório: {SEM_FONTE} — o valor do DIFAL fica NULL."
        )
    return (ICMSCST.TRIBUTADA_INTEGRALMENTE, aliq, norma, origem, None, msgs)


def _mensagem_zfm(deson: dict, suframa: str) -> str:
    v = f"R$ {deson['vICMSDeson']:.2f}".replace(".", ",")
    return (
        "Mercadoria destinada à Zona Franca de Manaus — isenta de ICMS nos termos do Convênio ICM 65/88 "
        f"e do Decreto-Lei 288/1967, art. 4º. Valor do ICMS desonerado {v}, abatido do preço "
        "(Convênio ICM 65/88, cláusula primeira, §1º). Inscrição SUFRAMA do destinatário: "
        f"{suframa}. IPI isento — {N_ZFM_IPI}. PIS/COFINS com alíquota zero — {N_ZFM_PISCOFINS}."
    )


def calcular_puro(
    empresa: dict,
    produto: dict,
    destinatario: dict,
    operacao: str = "revenda",
) -> dict:
    """O cálculo, sem banco. `calcular()` é este mais a leitura da identidade da empresa."""
    regime = (empresa.get("regime_tributario") or "").strip().lower()
    uf_emit = _uf_da_empresa(empresa)
    destino = classificar_destino(uf_emit, destinatario)
    operacao = operacao if operacao in ("revenda", "producao") else "revenda"

    base = (_d(produto.get("valor")) * _d(produto.get("quantidade") or 1)).quantize(Decimal("0.01"))
    origem_merc = str(produto.get("origem") or "0")
    ncm = str(produto.get("ncm") or "").strip()
    cfop = _CFOP.get((destino, operacao))

    linhas: list[dict] = []
    mensagens: list[str] = []
    bloqueios = _bloqueios(empresa, destino)
    deson: dict | None = None
    cst_ou_csosn: str | None = None
    aliquota: Decimal | None = None
    origem_regra = ""

    # ── COMO A MERCADORIA ENTROU decide o CFOP e o CST da saída. Sem esse fato não há escolha.
    entrada_cst = str(produto.get("icms_entrada_cst") or "").strip()
    entrada = classificar_entrada(entrada_cst)
    entrada_fonte = str(produto.get("icms_entrada_fonte") or "").strip()
    norma_cfop, origem_cfop = N_CFOP, f"destino «{DESTINOS[destino]}» × operação «{operacao}»"
    recusa: str | None = None
    if entrada is None:
        qual = ""
        if produto.get("codigo"):
            qual = f" — produto «{produto['codigo']}»"
        elif ncm:
            qual = f" — NCM {ncm}"
        if entrada_cst:
            qual += (
                f" (a nota de entrada trouxe CST/CSOSN de ICMS «{entrada_cst}», que não é nem "
                "tributação normal nem ICMS retido por ST: redução de base, suspensão, isenção "
                "ou diferimento não têm tratamento de saída com fonte aqui)"
            )
        recusa = MSG_ENTRADA_DESCONHECIDA.format(qual=qual)
    elif entrada == "st":
        if operacao == "revenda" and destino.startswith("interna"):
            cfop = CFOP_ST_INTERNA_REVENDA
            norma_cfop, origem_cfop = N_CFOP_5405, O_ENTRADA_ST
        else:
            recusa = MSG_ST_SEM_FONTE.format(cst=entrada_cst, destino=DESTINOS[destino].lower(), operacao=operacao)
    if recusa:
        bloqueios.append(recusa)
        cfop = None
        norma_cfop, origem_cfop = N_CFOP, SEM_FONTE

    linhas.append(_linha("CFOP", cfop, norma_cfop, origem_cfop))
    linhas.append(
        _linha(
            "Como a mercadoria entrou",
            entrada_cst or None,
            N_ENTRADA,
            entrada_fonte
            or (
                O_ENTRADA_ST
                if entrada == "st"
                else O_ENTRADA_NORMAL
                if entrada == "normal"
                else "desconhecido — nenhuma NF-e de entrada registrada para este produto"
            ),
        )
    )
    linhas.append(
        _linha("CRT do emitente", crt_do_regime(regime), N_CRT, f"empresas.regime_tributario = {regime or '(vazio)'}")
    )
    linhas.append(
        _linha(
            "Origem da mercadoria",
            origem_merc,
            "MOC NF-e 4.00, grupo N — Tabela A (origem da mercadoria)",
            "informada no produto; 0 = nacional",
        )
    )

    if recusa:
        # Não se sabe como entrou (ou entrou com ST numa operação sem fonte). Nada é escolhido:
        # nem CST, nem alíquota. O bloqueio já está na lista e o emissor recusa a nota.
        linhas.append(_linha("CST / CSOSN", None, N_ENTRADA, SEM_FONTE + " — " + recusa[:180]))
        linhas.append(_linha("Alíquota de ICMS", None, N_ENTRADA, SEM_FONTE))
    elif regime == "simples_nacional":
        # LC 123 art. 18: o ICMS está no DAS. Não há alíquota a destacar na nota.
        # ATENÇÃO ao nome do enum no repositório: `ICMSCSOSN.TRIBUTADA_COM_CREDITO` vale "102",
        # que na Tabela B do Ajuste SINIEF 07/2005 é «tributada SEM permissão de crédito» (o COM
        # crédito é o 101). O rótulo está trocado lá; o VALOR está certo. Usamos o valor.
        if entrada == "st":
            # Optante do Simples revendendo mercadoria já substituída: CSOSN 500, não 102.
            cst_ou_csosn = CSOSN_SAIDA_ST  # "500"
            origem_regra = N_CSOSN_500 + " — " + O_ENTRADA_ST
            linhas.append(_linha("CSOSN", cst_ou_csosn, N_CSOSN_500, O_ENTRADA_ST))
            linhas.append(
                _linha("Alíquota de ICMS", None, N_CST_60, "ICMS já retido por ST na entrada — nada a destacar")
            )
        else:
            cst_ou_csosn = ICMSCSOSN.TRIBUTADA_COM_CREDITO  # "102"
            origem_regra = N_CSOSN + " — CSOSN 102 (tributada sem permissão de crédito)"
            linhas.append(_linha("CSOSN", cst_ou_csosn, N_CSOSN, "padrão da casa: não transfere crédito"))
            linhas.append(_linha("Alíquota de ICMS", None, N_SIMPLES, "ICMS recolhido no DAS — não se destaca na NF-e"))
        linhas.append(
            _linha(
                "Crédito de ICMS ao destinatário",
                None,
                "LC 123/2006, art. 23, §1º",
                "CSOSN 101 só se a empresa OPTAR por transferir crédito — hoje não optou: " + SEM_FONTE,
            )
        )
        linhas.append(_linha("PIS / COFINS", None, N_SIMPLES, "dentro do DAS — CST 49/99, sem destaque"))
        linhas.append(_linha("IPI", None, N_SIMPLES, "dentro do DAS — sem destaque"))
        mensagens.append(
            "Documento emitido por ME/EPP optante pelo Simples Nacional — não gera direito a crédito de "
            "ICMS/IPI (LC 123/2006, art. 23)."
        )
    elif crt_do_regime(regime) == "3":
        cst, aliquota, norma_i, origem_i, deson, msgs = _icms_regime_normal(destino, base, origem_merc, entrada)
        cst_ou_csosn = cst
        origem_regra = origem_i
        mensagens.extend(msgs)
        linhas.append(_linha("CST de ICMS", str(cst), N_CST, origem_i))
        linhas.append(
            _linha(
                "Base de cálculo do ICMS",
                0.0 if entrada == "st" else _cent(base),
                N_CST,
                "ICMS retido na entrada: BC zero na saída (é o que a NF-e 10.026 traz)"
                if entrada == "st"
                else "valor do produto × quantidade",
            )
        )
        linhas.append(_linha("Alíquota de ICMS", aliquota, norma_i, origem_i))
        if deson:
            linhas.append(_linha("vICMSDeson", deson["vICMSDeson"], deson["norma"], deson["origem_regra"]))
            linhas.append(_linha("motDesICMS", "7 (SUFRAMA)", deson["norma"], deson["origem_regra"]))
            linhas.append(_linha("PIS / COFINS", Decimal("0.00"), N_ZFM_PISCOFINS, "CST 06 — alíquota zero"))
            linhas.append(_linha("IPI", None, N_ZFM_IPI, "isento (CST 52) — equiparação a industrial: " + SEM_FONTE))
        elif _proc := str(empresa.get("pis_cofins_processo") or "").strip():
            # Liminar viva: sai ZERADO, com o processo citado como fonte na própria linha.
            _norma = N_PIS_COFINS_LIMINAR.format(proc=_proc)
            linhas.append(
                _linha("PIS", Decimal("0.00"), _norma, f"CST {CST_PIS_COFINS_LIMINAR} — suspenso por decisão judicial")
            )
            linhas.append(
                _linha(
                    "COFINS", Decimal("0.00"), _norma, f"CST {CST_PIS_COFINS_LIMINAR} — suspenso por decisão judicial"
                )
            )
            mensagens.append(f"PIS e COFINS com exigibilidade suspensa por decisão judicial — processo nº {_proc}.")
        else:
            linhas.append(_linha("PIS", PIS_NAO_CUMULATIVO, N_PIS_COFINS, O_PIS_COFINS + " — CST 01"))
            linhas.append(_linha("COFINS", COFINS_NAO_CUMULATIVO, N_PIS_COFINS, O_PIS_COFINS + " — CST 01"))
            linhas.append(
                _linha(
                    "IPI",
                    None,
                    N_IPI_CONTRIB,
                    "empresa de revenda não é contribuinte do IPI; equiparação a industrial: " + SEM_FONTE,
                )
            )
    else:
        bloqueios.append(
            f"Regime tributário de {empresa.get('cnpj')} = «{regime or 'vazio'}» — não dá para derivar o "
            "CRT nem escolher entre CST e CSOSN. " + SEM_FONTE
        )
        linhas.append(_linha("CST / CSOSN", None, N_CRT, SEM_FONTE))

    linhas.append(
        _linha(
            "Substituição tributária",
            {"st": "ICMS já retido na entrada — saída sem novo destaque", "normal": "não — entrou tributada"}.get(
                entrada or ""
            ),
            N_ST if entrada is None else N_CST_60,
            O_ST if entrada is None else (O_ENTRADA_ST if entrada == "st" else O_ENTRADA_NORMAL),
        )
    )
    if ncm:
        linhas.append(
            _linha(
                "NCM",
                ncm,
                N_TIPI,
                "ncms tem 10.515 códigos com descrição e ZERO alíquota no banco — "
                "ipi_aliquota/pis_aliquota/cofins_aliquota/icms_cest/icms_st_mva todos NULL",
            )
        )

    valor = None if aliquota is None else _cent(base * aliquota / 100)
    if entrada == "st" and not recusa:
        # zero MEDIDO, não desconhecido: a NF-e 10.026 traz BC ICMS 0,00 e V.ICMS 0,00.
        valor = 0.0
        mensagens.append(
            "Mercadoria com ICMS retido anteriormente por substituição tributária — "
            "CST 060, sem novo destaque de ICMS nesta operação (" + N_CST_60 + ")."
        )
    if deson:
        mensagens.insert(0, _mensagem_zfm(deson, _digitos(destinatario.get("suframa"))))

    return {
        "cfop": cfop,
        "cst_ou_csosn": str(cst_ou_csosn) if cst_ou_csosn else None,
        "base": 0.0 if (entrada == "st" and not recusa) else _cent(base),
        "icms_entrada_cst": entrada_cst or None,
        "icms_entrada_situacao": entrada,
        "aliquota": None if aliquota is None else float(aliquota),
        "valor": valor,
        "deson": deson,
        "mensagem_fiscal": " ".join(mensagens),
        "origem_regra": origem_regra or SEM_FONTE,
        # extras que a tela usa — a régua é ESTA. A tela não tem régua própria.
        "destino": destino,
        "destino_label": DESTINOS[destino],
        "operacao": operacao,
        "regime": regime,
        "crt": crt_do_regime(regime),
        "uf_emitente": uf_emit,
        "linhas": linhas,
        "bloqueios": bloqueios,
    }


async def calcular(
    db,
    empresa_cnpj: str,
    produto: dict,
    destinatario: dict,
    operacao: str = "revenda",
) -> dict:
    """Resolve a empresa pelo CNPJ e devolve o cálculo. Único I/O: a tabela `empresas`."""
    from modules.empresas.services.empresa_lookup import get_empresa

    empresa = await get_empresa(db, cnpj=empresa_cnpj)
    r = calcular_puro(empresa, produto, destinatario, operacao)
    r["empresa"] = {
        "cnpj": empresa.get("cnpj"),
        "nome": empresa.get("nome_fantasia") or empresa.get("razao_social"),
        "slug": empresa.get("slug"),
        "inscricao_estadual": empresa.get("inscricao_estadual"),
        "inscricao_suframa": empresa.get("inscricao_suframa"),
    }
    return r


# ── empresas do autoteste: cópia fiel do que está em `empresas` hoje (24/09/2026).
_ELETRONICA = {
    "cnpj": "35.710.481/0001-03", "slug": "conecta_eletronica", "nome_fantasia": "Conecta Mais Eletrônica",
    "regime_tributario": "lucro_real", "inscricao_estadual": "05.426.574-6",
    "inscricao_suframa": "210140500", "codigo_municipio_ibge": "1302603",
}  # fmt: skip
_PATRIMONIAL = {
    "cnpj": "66.014.833/0001-10", "slug": "conecta_patrimonial", "nome_fantasia": "Conecta Mais Patrimonial",
    "regime_tributario": "simples_nacional", "inscricao_estadual": None,
    "inscricao_suframa": None, "codigo_municipio_ibge": "1302603",
}  # fmt: skip
#: emitente fictício de FORA do AM — o único jeito de o ramo ZFM 6109/6110 ser alcançado
_DE_FORA = dict(_ELETRONICA, codigo_municipio_ibge="3550308", cnpj="00.000.000/0001-00",
                nome_fantasia="(fictícia, fora do AM)")  # fmt: skip

EMPRESAS_DEMO = {"conecta_eletronica": _ELETRONICA, "conecta_patrimonial": _PATRIMONIAL, "_de_fora": _DE_FORA}
#: produto do autoteste que ENTROU tributado (CST 00 na nota do fornecedor) — 43 dos 95 de
#: `fin_produtos` são assim.
PROD = {"ncm": "85311000", "valor": 1000, "quantidade": 1, "origem": "0", "icms_entrada_cst": "00"}
#: produto que ENTROU com o ICMS já retido por ST (CST 60) — 43 dos 95. Sai 5405 / 060 / zero.
PROD_ST = dict(PROD, icms_entrada_cst="60")
#: produto sem entrada conhecida — o sistema NÃO escolhe CFOP para ele. 9 dos 95 (CST 20/41/50,
#: CSOSN 400 e 2 itens sem grupo de ICMS) caem aqui, e os 810 de `products` sem compra também.
PROD_SEM_ENTRADA = {"ncm": "85311000", "valor": 1000, "quantidade": 1, "origem": "0", "codigo": "SEM-ENTRADA"}


def demo() -> None:
    """Autoteste sem banco: `python3 -m modules.fiscal.services.tributacao_nfe`."""
    am_c = {"uf": "AM", "contribuinte": True, "suframa": None}
    am_nc = {"uf": "AM", "contribuinte": False, "suframa": None}
    sp_c = {"uf": "SP", "contribuinte": True, "suframa": None}
    sp_nc = {"uf": "SP", "contribuinte": False, "suframa": None}
    am_suf = {"uf": "AM", "contribuinte": True, "suframa": "210140500"}

    # 1. lucro real, venda interna no AM → 5102 / CST 00 / 20% / R$ 200,00
    r = calcular_puro(_ELETRONICA, PROD, am_c)
    assert (r["cfop"], r["cst_ou_csosn"], r["crt"]) == ("5102", "00", "3"), r
    assert r["aliquota"] == 20.0 and r["valor"] == 200.0 and r["base"] == 1000.0, r
    assert r["deson"] is None and not r["bloqueios"], r

    # 2. lucro real, interestadual a contribuinte → 6102 / 12% (Senado 22/89)
    r = calcular_puro(_ELETRONICA, PROD, sp_c)
    assert (r["cfop"], r["aliquota"], r["valor"]) == ("6102", 12.0, 120.0), r

    # 3. mercadoria importada, interestadual → 4% (Senado 13/2012)
    r = calcular_puro(_ELETRONICA, dict(PROD, origem="1"), sp_c)
    assert r["aliquota"] == 4.0 and "13/2012" in r["origem_regra"], r

    # 4. não contribuinte em outro estado → 6108 + DIFAL sem número (sem fonte)
    r = calcular_puro(_ELETRONICA, PROD, sp_nc)
    assert r["cfop"] == "6108" and SEM_FONTE in r["mensagem_fiscal"], r

    # 5. não contribuinte DENTRO do AM → segue interna
    assert calcular_puro(_ELETRONICA, PROD, am_nc)["cfop"] == "5102"

    # 6. O ACHADO: SUFRAMA do destinatário com emitente de Manaus NÃO é venda para a ZFM
    r = calcular_puro(_ELETRONICA, PROD, am_suf)
    assert r["destino"] == "interna_contribuinte" and r["cfop"] == "5102", r
    assert r["deson"] is None and r["aliquota"] == 20.0, r

    # 7. emitente de FORA vendendo para a ZFM → 6110 / CST 40 / desoneração + mensagem fiscal
    r = calcular_puro(_DE_FORA, PROD, am_suf)
    assert (r["destino"], r["cfop"], r["cst_ou_csosn"]) == ("zfm_entrante", "6110", "40"), r
    assert r["aliquota"] is None and r["deson"]["vICMSDeson"] == 120.0, r
    assert r["deson"]["motDesICMS"] == "7", r
    for pedaco in ("65/88", "288/1967", "SUFRAMA", "210140500", "10.996/2004", "7.212/2010"):
        assert pedaco in r["mensagem_fiscal"], pedaco

    # 8. produção própria troca o CFOP, não o tributo
    assert calcular_puro(_ELETRONICA, PROD, am_c, "producao")["cfop"] == "5101"
    assert calcular_puro(_DE_FORA, PROD, am_suf, "producao")["cfop"] == "6109"

    # 9. Simples: CSOSN sempre, CST de regime normal nunca; e sem IE a nota está bloqueada
    for dest in (am_c, am_nc, sp_c, sp_nc, am_suf):
        r = calcular_puro(_PATRIMONIAL, PROD, dest)
        assert (r["cst_ou_csosn"], r["crt"]) == ("102", "1"), r
        assert r["aliquota"] is None and r["valor"] is None, r
        assert any("Inscrição Estadual" in x for x in r["bloqueios"]), r

    # 10. nenhuma linha sem norma e sem origem_regra, em NENHUMA combinação
    n = 0
    for emp in (_ELETRONICA, _PATRIMONIAL, _DE_FORA):
        for dest in (am_c, am_nc, sp_c, sp_nc, am_suf):
            for op in ("revenda", "producao"):
                r = calcular_puro(emp, PROD, dest, op)
                assert r["cfop"], (emp["slug"], dest, op)
                assert r["origem_regra"], r
                for ln in r["linhas"]:
                    assert ln["norma"] and ln["origem_regra"], ln
                n += 1
    assert n == 30, n

    # ───────────────────────── AA5: o imposto que já foi pago ─────────────────────────
    # 11. mercadoria que ENTROU com ICMS-ST sai 5405 / CST 060 / ICMS ZERO — é a NF-e 10.026.
    for dest in (am_c, am_nc):
        r = calcular_puro(_ELETRONICA, PROD_ST, dest)
        assert (r["cfop"], r["cst_ou_csosn"]) == ("5405", "60"), r
        assert r["aliquota"] is None and r["valor"] == 0.0 and r["base"] == 0.0, r
        assert not r["bloqueios"], r
        assert "substituição tributária" in r["mensagem_fiscal"], r

    # 12. sem saber como entrou, NÃO se escolhe CFOP: recusa que ensina, nada de chute.
    r = calcular_puro(_ELETRONICA, PROD_SEM_ENTRADA, am_c)
    assert r["cfop"] is None and r["cst_ou_csosn"] is None and r["aliquota"] is None, r
    assert any("Não sei como esta mercadoria entrou" in x for x in r["bloqueios"]), r
    assert "SEM-ENTRADA" in " ".join(r["bloqueios"]), r

    # 13. CST de entrada sem tratamento (20 redução, 41 não tributada, 50 suspensão) → recusa.
    for cst in ("20", "41", "50", "51", "400", "90"):
        r = calcular_puro(_ELETRONICA, dict(PROD, icms_entrada_cst=cst), am_c)
        assert r["cfop"] is None and r["bloqueios"], (cst, r)

    # 14. ST fora da venda interna em revenda não é chutada: recusa declarada «sem fonte».
    for dest in (sp_c, sp_nc):
        r = calcular_puro(_ELETRONICA, PROD_ST, dest)
        assert r["cfop"] is None and any(SEM_FONTE in x for x in r["bloqueios"]), r
    r = calcular_puro(_ELETRONICA, PROD_ST, am_c, "producao")
    assert r["cfop"] is None and r["bloqueios"], r

    # 15. Simples revendendo mercadoria já substituída: CSOSN 500, não 102.
    r = calcular_puro(_PATRIMONIAL, PROD_ST, am_c)
    assert (r["cfop"], r["cst_ou_csosn"]) == ("5405", "500"), r
    assert r["aliquota"] is None, r

    # 16. «060» da DANFE e «60» do XML são o mesmo fato; CSOSN 500 não é desmontado.
    assert classificar_entrada("060") == "st" and classificar_entrada("60") == "st"
    assert classificar_entrada("500") == "st" and classificar_entrada("102") == "normal"
    assert classificar_entrada("000") == "normal" and classificar_entrada("") is None
    assert classificar_entrada("53") is None and classificar_entrada("99") is None

    print(f"demo tributacao_nfe: OK — 16 blocos, {n} combinações empresa × destino × operação")


if __name__ == "__main__":
    demo()
