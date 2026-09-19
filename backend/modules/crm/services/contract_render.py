"""Renderiza o contrato REAL a partir do modelo cadastrado — a costura que faltava.

O CRM tinha o CRUD de `contract_templates` (corpo de 27 mil caracteres, 12 cláusulas)
e tinha o gerador de PDF, e nada juntava os dois: `GET /contracts/{id}/pdf` montava um
molde fixo de 3 páginas. O contrato de verdade vivia num .docx fora do sistema.

TRÊS DECISÕES QUE VALEM MAIS QUE O CÓDIGO:

1 · `StrictUndefined`, igual ao motor do DP (`contract_generator_service`).
    Variável faltando ESTOURA. Contrato que sai com `{{ valor_mensal_fmt }}` impresso, ou
    com o campo vazio, vai para assinatura assim — é pior que erro visível.

2 · O CNPJ da CONTRATADA vem do TIPO DE SERVIÇO, não do que estiver gravado.
    Regra do Jordan (19/08): mão de obra sai pela PATRIMONIAL, eletrônica pela ELETRÔNICA.
    E há motivo concreto: em 19/08 o contrato de portaria do Green Hills (CTR-2026-00019,
    R$ 22.100) estava com `empresa_id` da ELETRÔNICA no banco, e o .docx de origem assinava
    com o CNPJ dela. Errar CNPJ em contrato de prestação é problema fiscal e trabalhista.
    Por isso este módulo RESOLVE pela regra e RECUSA quando a fonte é ambígua, em vez de
    aceitar o que está gravado.

3 · Não invento tipo de serviço. Se o contrato não declara e o modelo não declara, o render
    falha com mensagem clara. Chutar a contratada é exatamente o defeito que ele existe
    para impedir.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from decimal import Decimal

from jinja2 import StrictUndefined, Template
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.crm.services import pdf_branding as B  # noqa: N812 — `B.` curto no meio do layout

# ── As duas prestadoras. Fonte: tabela `empresas` (conferido 19/08). Ficam aqui como
#    constante de REGRA, não de dado: a resolução tem de ser determinística e testável
#    mesmo que alguém edite a linha da empresa.
# Razão social COMO APARECE NO CONTRATO. Decisão do Jordan (21/08): na Receita a
# contadora registrou "CONECTAMAIS" tudo junto; a grafia correta da marca é "Conecta Mais",
# separado, e é assim que ele quer no instrumento. O CNPJ — que é o que identifica a parte —
# permanece o registrado, então a diferença é de grafia, não de pessoa jurídica.
PATRIMONIAL = ("Conecta Mais Patrimonial LTDA", "66.014.833/0001-10")
ELETRONICA = ("Conecta Mais Eletrônica LTDA", "35.710.481/0001-03")

# Sede de cada prestadora, CONFERIDA NA RECEITA FEDERAL em 21/08/2026 — fonte da verdade
# declarada pelo Jordan. As duas fontes que eu vinha usando estavam erradas:
#   · pdf_branding dizia "Rua Victor Hughes, 19 — Parque 10 de Novembro" para a
#     Patrimonial: faltavam o complemento (Conjunto Castelo Branco) e o CEP;
#   · o .docx dava a ELETRÔNICA em "Rua 42, nº 16, Conj. Castelo Branco II, Parque Dez de
#     Novembro, CEP 69055-600" — endereço COMPLETAMENTE diferente do registrado.
# Se o cadastro na Receita mudar, isto tem de ser reconferido (não há sincronismo).
_SEDE = {
    PATRIMONIAL[1]: "Rua Victor Hughes, 19, Conjunto Castelo Branco, Parque 10 de Novembro, CEP 69055-630, Manaus/AM",
    ELETRONICA[1]: "Rua Nova Palestina, 51, Crespo, CEP 69073-488, Manaus/AM",
}


# Partículas que ficam em minúscula no meio do nome, e siglas que ficam em caixa alta.
_MINUSC = {"de", "da", "do", "das", "dos", "e", "di", "del", "van", "von", "a"}
_SIGLAS = {"ltda", "me", "epp", "eireli", "s/a", "sa", "s.a", "cnpj", "cpf", "ii", "iii", "iv"}
# Acentos que o cadastro perde por ser digitado em caixa alta sem acentuação.
_ACENTO = {
    "condominio": "Condomínio",
    "servicos": "Serviços",
    "comercio": "Comércio",
    "seguranca": "Segurança",
    "tecnologia": "Tecnologia",
    "eletronica": "Eletrônica",
    "predial": "Predial",
    "sao": "São",
    "jose": "José",
    "antonio": "Antônio",
}


def nome_proprio(v: str | None) -> str:
    """Padroniza nome de pessoa e de empresa para Capitulação de Título.

    Decisão do Jordan (21/08): ou TODOS em caixa alta, ou NINGUÉM. O contrato saía com o
    condomínio e o síndico em MAIÚSCULAS (vêm do cadastro assim) e a Conecta Mais e o
    Jordan em caixa mista — quatro partes, dois estilos, no mesmo parágrafo.
    Escolhida a caixa mista porque ele já pediu "Conecta Mais Patrimonial LTDA" e não
    "CONECTA MAIS...". Trocar para caixa alta é mudar esta função num ponto só.

    Só reescreve quando o texto está TODO em maiúsculas — nome já digitado corretamente
    passa intacto, para não estragar grafia que alguém cuidou de escrever.
    """
    v = (v or "").strip()
    if not v or v != v.upper():
        return v
    saida = []
    for i, palavra in enumerate(v.split()):
        base = palavra.lower()
        if base in _SIGLAS:
            saida.append(palavra.upper())
        elif base in _ACENTO:
            saida.append(_ACENTO[base])
        elif i > 0 and base in _MINUSC:
            saida.append(base)
        else:
            saida.append(base[:1].upper() + base[1:])
    return " ".join(saida)


def _cpf_rg(notes: str | None) -> tuple[str, str]:
    """Extrai CPF e RG de `crm_contacts.notes`, que é texto livre.

    O contato do Green Hills guardou só o CPF cru ("562.043.372-20"), e o modelo de portaria
    lê esse campo como CPF — por isso o fallback devolve o texto inteiro. Quem tiver RG grava
    "CPF 000.000.000-00 · RG 1234567 SSP/AM" e os dois saem separados.
    """
    n = (notes or "").strip()
    m_cpf = re.search(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}", n)
    m_rg = re.search(r"RG[:\s]*([0-9A-Za-z.\-/]+(?:\s+[A-Z]{2,4}(?:/[A-Z]{2})?)?)", n)
    return (m_cpf.group(0) if m_cpf else n), (m_rg.group(1).strip() if m_rg else "")


def cnpj_fmt(v: str | None) -> str:
    """00.000.000/0000-00. O cadastro guarda sem máscara e o contrato imprimia
    "CNPJ nº 08063476000183" — o resto do documento usa a forma pontuada."""
    d = re.sub(r"\D", "", v or "")
    if len(d) != 14:
        return v or ""
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


# Vocabulário REAL de `contracts.tipo_servico`, medido em 19/08:
#   maodeobra 8 · manutencao_cftv 3 · portaria_remota 2 · NULL 2
# e de `contract_templates.service_type`: portaria_mao_de_obra, ferias, admissao.
# Os dois vocabulários NÃO coincidem — por isso o mapa aceita as duas grafias.
_MAO_DE_OBRA = {"maodeobra", "mao_de_obra", "portaria_mao_de_obra", "portaria_presencial", "limpeza", "servicos_gerais"}
_ELETRONICA = {
    "manutencao_cftv",
    "portaria_remota",
    "seguranca_eletronica",
    "cftv",
    "alarme",
    "controle_acesso",
    "eletronica_servico_unico",
}


class RenderError(RuntimeError):
    """Falha que NÃO deve virar PDF. Sempre com o motivo em português, para chegar na tela."""


@dataclass
class Contratada:
    razao_social: str
    cnpj: str
    origem: str  # de onde saiu a decisão — vai no relatório, não no contrato
    divergencia: str | None = None  # empresa_id gravada contradiz a regra


def resolver_contratada(
    tipo_servico: str | None, service_type_modelo: str | None, empresa_gravada_cnpj: str | None = None
) -> Contratada:
    """Decide QUEM presta, pela regra — e denuncia quando o gravado contradiz.

    Ordem: o tipo do CONTRATO manda; se ele for nulo, vale o do MODELO (renderizar com um
    modelo de mão de obra é declarar que é mão de obra). Se os dois forem nulos, recusa.
    """

    def classificar(v: str | None) -> str | None:
        if not v:
            return None
        k = v.strip().lower()
        if k in _MAO_DE_OBRA:
            return "maodeobra"
        if k in _ELETRONICA:
            return "eletronica"
        return None

    do_contrato = classificar(tipo_servico)
    do_modelo = classificar(service_type_modelo)

    if do_contrato and do_modelo and do_contrato != do_modelo:
        raise RenderError(
            f"Contradição: o contrato é '{tipo_servico}' e o modelo é '{service_type_modelo}'. "
            "Um deles está errado — corrija antes de gerar o contrato."
        )

    escolhido = do_contrato or do_modelo
    if not escolhido:
        raise RenderError(
            "Não dá para saber quem presta o serviço: o contrato não tem `tipo_servico` e o "
            "modelo não tem `service_type`. Preencha um dos dois — chutar a contratada "
            "colocaria o CNPJ errado num contrato assinado."
        )

    razao, cnpj = PATRIMONIAL if escolhido == "maodeobra" else ELETRONICA
    origem = "contrato.tipo_servico" if do_contrato else "modelo.service_type"

    diverg = None
    if empresa_gravada_cnpj:
        grav = re.sub(r"\D", "", empresa_gravada_cnpj)
        if grav and grav != re.sub(r"\D", "", cnpj):
            diverg = (
                f"o contrato aponta empresa_id de CNPJ {empresa_gravada_cnpj}, mas por "
                f"'{escolhido}' quem presta é {razao} ({cnpj})"
            )
    return Contratada(razao, cnpj, origem, diverg)


# ── Valor por extenso ────────────────────────────────────────────────────────────────
_UNI = [
    "",
    "um",
    "dois",
    "três",
    "quatro",
    "cinco",
    "seis",
    "sete",
    "oito",
    "nove",
    "dez",
    "onze",
    "doze",
    "treze",
    "quatorze",
    "quinze",
    "dezesseis",
    "dezessete",
    "dezoito",
    "dezenove",
]
_DEZ = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"]
_CEM = [
    "",
    "cento",
    "duzentos",
    "trezentos",
    "quatrocentos",
    "quinhentos",
    "seiscentos",
    "setecentos",
    "oitocentos",
    "novecentos",
]


def _ate_999(n: int) -> str:
    if n == 0:
        return ""
    if n == 100:
        return "cem"
    c, r = divmod(n, 100)
    partes = []
    if c:
        partes.append(_CEM[c])
    if r:
        if r < 20:
            partes.append(_UNI[r])
        else:
            d, u = divmod(r, 10)
            partes.append(_DEZ[d] + (f" e {_UNI[u]}" if u else ""))
    return " e ".join(partes)


def por_extenso(v: Decimal | float | int) -> str:
    """Reais por extenso. Existe porque o contrato exige e errar valor por extenso invalida."""
    v = Decimal(str(v)).quantize(Decimal("0.01"))
    inteiro, cent = int(v), int((v - int(v)) * 100)
    if inteiro == 0 and cent == 0:
        return "zero reais"
    partes: list[str] = []
    milhoes, resto = divmod(inteiro, 1_000_000)
    milhares, unidades = divmod(resto, 1_000)
    if milhoes:
        partes.append(f"{_ate_999(milhoes)} {'milhão' if milhoes == 1 else 'milhões'}")
    if milhares:
        partes.append("mil" if milhares == 1 else f"{_ate_999(milhares)} mil")
    if unidades:
        partes.append(_ate_999(unidades))
    partes = [p for p in partes if p]
    # A conjunção NÃO é uniforme em português: "mil DUZENTOS e trinta e quatro" (sem "e"),
    # mas "mil E CEM" e "mil E vinte" (com). A regra é: só liga com "e" quando o último
    # bloco é menor que 100 ou é centena redonda. Escrever tudo com " e " produzia
    # "mil e duzentos e trinta e quatro reais" — constrangedor num contrato assinado.
    if len(partes) > 1 and unidades and not (unidades < 100 or unidades % 100 == 0):
        txt = " ".join(partes[:-1]) + " " + partes[-1]
    else:
        txt = " e ".join(partes)
    # "um milhão DE reais" — a preposição só aparece quando o número TERMINA em
    # milhão/milhões (um milhão e quinhentos mil reais NÃO leva "de").
    if inteiro == 1:
        txt += " real"
    elif milhoes and not milhares and not unidades:
        txt += " de reais"
    else:
        txt += " reais"
    if cent:
        txt += f" e {_ate_999(cent)} {'centavo' if cent == 1 else 'centavos'}"
    return txt.strip()


def brl(v: Decimal | float | int) -> str:
    return f"R$ {Decimal(str(v)):,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


_MES_PT = [
    "",
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
]


def data_extenso(d) -> str:
    """1º de setembro de 2026 — a forma que o contrato usa para datas de vigência."""
    if not d:
        return ""
    dia = "1º" if d.day == 1 else str(d.day)
    return f"{dia} de {_MES_PT[d.month]} de {d.year}"


_NUM_EXT = {
    1: "um",
    2: "dois",
    3: "três",
    4: "quatro",
    5: "cinco",
    6: "seis",
    7: "sete",
    8: "oito",
    9: "nove",
    10: "dez",
    12: "doze",
    15: "quinze",
    20: "vinte",
    24: "vinte e quatro",
    30: "trinta",
    36: "trinta e seis",
    48: "quarenta e oito",
    60: "sessenta",
}


def num_extenso(n: int) -> str:
    return _NUM_EXT.get(n) or _ate_999(n) or str(n)


def num_par(n: int) -> str:
    """Número + extenso entre parênteses, na forma que o contrato usa.

    O .docx de origem escreve "90 (noventa) dias", "24 (vinte e quatro) meses",
    "04 (quatro) agentes" e "dia 05 (cinco)" — sempre o algarismo E o extenso, com zero
    à esquerda até 9. As variáveis do modelo se chamam *_extenso mas ocupam a posição
    inteira ("{{var}} dias"), então devolver só "noventa" descaracterizava a redação
    jurídica. Aqui a forma volta a ser a do documento.
    """
    return f"{n:02d} ({num_extenso(n)})"


# ── Contexto ─────────────────────────────────────────────────────────────────────────
_SQL_CONTRATO = """
SELECT c.id::text, c.contract_number, c.name, c.monthly_value, c.start_date, c.end_date,
       c.contract_type::text AS contract_type,
       c.total_value,
       c.description,
       c.tipo_servico::text  AS tipo_servico,
       c.template_id::text   AS template_id,
       c.payment_day,
       c.grace_period_days,
       c.notice_period_days,
       c.renewal_notification_days,
       c.sla_config,
       c.empresa_id::text    AS empresa_id,
       cl.name               AS cliente_nome,
       cl.document_number    AS cliente_cnpj,

       -- endereço vem em 6 colunas separadas (não existe `address` em clients)
       trim(both ', ' FROM concat_ws(', ',
            nullif(concat_ws(', ', cl.address_street, cl.address_number), ''),
            nullif(cl.address_neighborhood, ''),
            nullif(concat_ws('/', cl.address_city, cl.address_state), ''),
            nullif(cl.address_zipcode, ''))) AS cliente_endereco,
       -- ⭐ 18/09/2026: cidade e UF SEPARADAS, porque `cidade_assinatura` precisa delas
       -- sozinhas. Estavam só dentro do concat do endereço, e `_foro_e_cidade` não tinha
       -- como alcançá-las — a cadeia de origem pularia direto para o default.
       cl.address_city       AS cliente_cidade,
       cl.address_state      AS cliente_uf,
       e.cnpj                AS empresa_gravada_cnpj
FROM contracts c
LEFT JOIN clients cl ON cl.id = c.client_id
LEFT JOIN empresas e ON e.id = c.empresa_id
WHERE c.id::text = :k OR c.contract_number = :k
"""


# Representante legal do CONTRATANTE: quem assina pelo condomínio. Mora em `crm_contacts`
# — a tabela já tem a forma certa (client_id/name/role) e não precisa de coluna nova.
# `clients` NÃO tem campo de representante (conferido 19/08), e contato financeiro/técnico
# não serve: quem paga e quem entende de câmera não são quem assina.
_SQL_REPRESENTANTE = """
SELECT k.name, k.notes, k.role
FROM crm_contacts k JOIN contracts c ON c.client_id = k.client_id
WHERE (c.id::text = :k OR c.contract_number = :k)
  -- ⚠️ VOCABULÁRIO, não lista de cargos conhecidos. Em 11/09/2026 corrigi o cadastro da
  -- síndica do Maiápolis de 'Representante legal' para 'Presidente' — que é o cargo real
  -- dela numa Associação — e o contrato PAROU de emitir: o filtro não conhecia a palavra e
  -- concluiu "não há representante cadastrado". Filtro literal que não conhece o cargo real
  -- recusa um signatário legítimo, e recusar é pior que não filtrar: parece falta de
  -- cadastro quando o cadastro está mais correto do que antes.
  -- Os cinco lugares que faziam esta mesma pergunta foram corrigidos juntos.
  AND (k.role ILIKE '%representante%' OR k.role ILIKE '%s%ndic%' OR k.role ILIKE '%legal%' OR k.role ILIKE '%presidente%' OR k.role ILIKE '%diretor%' OR k.role ILIKE '%s%cio%' OR k.role ILIKE '%administrador%' OR k.role ILIKE '%procurador%' OR k.role ILIKE '%titular%')
ORDER BY k.is_primary DESC NULLS LAST, k.created_at
LIMIT 1
"""

_SQL_ITENS = """
SELECT i.service_name, i.description, i.quantity, i.unit_price, i.total_price,
       i.service_type, i.notes
FROM contract_items i JOIN contracts c ON c.id = i.contract_id
WHERE (c.id::text = :k OR c.contract_number = :k) AND coalesce(i.is_active, true)
ORDER BY i.created_at
"""


_MESES = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)


def _inventario(itens: list) -> str:
    """Os sistemas cobertos, um por linha — vêm de `contract_items`, não do texto.

    O inventário é o que define o preço da manutenção; deixá-lo escrito à mão no modelo
    faria todo condomínio herdar as cancelas do vizinho.
    """
    linhas = []
    for i in itens:
        nome = (i["service_name"] or "").strip()
        desc = (i["description"] or "").strip()
        linhas.append(f"• {nome}: {desc}" if desc else f"• {nome}")
    return "\n".join(linhas)


_SQL_CONTA = """
SELECT b.bank_name, b.bank_code, b.agency, b.agency_digit, b.account_number,
       b.account_digit, b.pix_key, b.pix_key_type
FROM bank_accounts b
WHERE b.empresa_id = :e AND coalesce(b.ativo, true) AND coalesce(b.allows_receipts, false)
  AND b.agency IS NOT NULL AND b.account_number IS NOT NULL
ORDER BY b.is_main_account DESC NULLS LAST, b.created_at
LIMIT 1
"""


async def _conta_da_empresa(db: AsyncSession, empresa_id) -> str:
    """Onde o cliente paga — vem de `bank_accounts` da empresa que EMITE o contrato.

    O contrato do Green Hills foi assinado dizendo quanto e quando, e nunca ONDE: o síndico
    ficou com um instrumento que não informa a conta. Aqui a conta segue o CNPJ emitente —
    Patrimonial recebe na dela, Eletrônica na dela — pelo mesmo caminho que resolve a
    CONTRATADA, para o dinheiro nunca cair na empresa errada num grupo de dois CNPJs.

    Exige conta com agência E número: meia conta num contrato é pior que nenhuma.
    """
    if not empresa_id:
        return ""
    r = (await db.execute(text(_SQL_CONTA), {"e": empresa_id})).mappings().first()
    if not r:
        return ""
    conta = f"{r['account_number']}-{r['account_digit']}" if r["account_digit"] else r["account_number"]
    ag = f"{r['agency']}-{r['agency_digit']}" if r["agency_digit"] else r["agency"]
    partes = [f"{r['bank_name']} ({r['bank_code']})", f"agência {ag}", f"conta corrente {conta}"]
    if r["pix_key"]:
        rotulo = {"cnpj": "CNPJ", "cpf": "CPF", "email": "e-mail", "telefone": "telefone"}.get(
            (r["pix_key_type"] or "").lower(), "chave"
        )
        partes.append(f"chave PIX ({rotulo}) {r['pix_key']}")
    return ", ".join(partes)


def _do_sla(sla: dict | None, chave: str, default=None):
    """Lê `contracts.sla_config`. Vazio devolve None e o render RECUSA — não inventa SLA."""
    if not isinstance(sla, dict):
        return default
    v = sla.get(chave)
    return default if v in (None, "") else v


def _composicao(itens: list) -> dict:
    """Quantos agentes de dia, quantos de noite, e o subtotal de cada turno.

    A composição vive em `contract_items` — a tabela existe com a forma exata
    (service_name/quantity/unit_price/total_price) e em 19/08 estava com ZERO linhas nos
    15 contratos. Enquanto ninguém preencher, o render RECUSA em vez de inventar: no
    .docx do Green Hills a tabela dizia "AGP Diurno 2 · AGP Noturno 2", e chutar isso
    num contrato assinado é pior do que não gerar.
    """
    dia = noite = 0
    v_dia = v_noite = Decimal("0")
    for it in itens:
        rotulo = f"{it['service_name'] or ''} {it['description'] or ''}".lower()
        qtd = int(it["quantity"] or 0)
        total = Decimal(str(it["total_price"] or 0))
        if "notur" in rotulo:
            noite += qtd
            v_noite += total
        elif "diurn" in rotulo or "dia" in rotulo:
            dia += qtd
            v_dia += total
    return {
        "qtd_diurno": str(dia) if dia else "",
        "qtd_noturno": str(noite) if noite else "",
        "valor_diurno_fmt": brl(v_dia) if v_dia else "",
        "valor_noturno_fmt": brl(v_noite) if v_noite else "",
        "qtd_agentes_extenso": num_par(dia + noite) if (dia + noite) else "",
    }


def _fem(n: int) -> str:
    """ "duas parcelas", não "dois parcelas".

    `num_extenso` é masculino porque nasceu para contar meses e dias. Aqui o substantivo é
    "parcela" — e o contrato saiu para conferência com "02 (dois) parcelas de R$ 7.720,00".
    Só 1 e 2 flexionam em português; de três em diante o masculino serve.
    """
    return {1: "uma", 2: "duas"}.get(n) or num_extenso(n)


def _venc(vencs: list[str]) -> str:
    """ "30 e 60 dias", não "30 dias e 60 dias" — a redação do contrato-base.

    Quando todos os vencimentos terminam na mesma unidade, ela só aparece no último.
    """
    if len(vencs) > 1:
        partes = [v.rsplit(" ", 1) for v in vencs]
        unid = {p[-1].lower() for p in partes if len(p) == 2}
        if len(unid) == 1 and all(len(p) == 2 for p in partes):
            return (
                ", ".join(p[0] for p in partes[:-1]) + f" e {vencs[-1]}"
                if len(vencs) > 2
                else f"{partes[0][0]} e {vencs[-1]}"
            )
    return " e ".join(vencs)


def _ctx_one_time(row, itens: list, template: dict) -> dict:
    """Variáveis do contrato de valor ÚNICO (fornecimento + instalação), não recorrente.

    Três fontes, nesta ordem de precedência — do mais específico para o mais geral:

        contracts.sla_config    o que muda por contrato (proposta, prazo, foro)
        template.variables      os defaults do MODELO (multa, garantia, cortesia)
        o código                nada. Faltou, o render RECUSA em `variaveis_vazias`.

    `sla_config` já é o saco de parâmetros por contrato nesta casa — é de lá que saem
    `visita_numero` e `visitas_mes` do modelo de manutenção. Reusar evita uma coluna nova
    e um `alembic upgrade heads` manual no meio de um bake.

    O cronograma de pagamento vem de `contract_items`, classificado por `service_type`:
    `entrada`, `parcela` e `retida`. Não é abuso da tabela: para um contrato de valor
    único, a composição do preço É o cronograma — do mesmo jeito que, no recorrente, é a
    lista de postos. A soma continua tendo de fechar com o total, e quem cobra isso é o
    wizard, antes de deixar emitir.
    """
    var = template.get("variables") if isinstance(template.get("variables"), dict) else {}
    sla = row["sla_config"] if isinstance(row["sla_config"], dict) else {}

    def par(nome, default=""):
        # o valor do CONTRATO ganha do default do MODELO; string vazia não conta como valor
        v = sla.get(nome)
        if v in (None, ""):
            v = var.get(nome)
        return default if v in (None, "") else v

    total = Decimal(str(row["total_value"] or 0))
    plus = Decimal(str(par("conecta_plus_valor", 0) or 0))

    def _dos(tipo):
        return [i for i in itens if (i["service_type"] or "").strip().lower() == tipo]

    entrada = sum((Decimal(str(i["total_price"] or 0)) for i in _dos("entrada")), Decimal(0))
    retida = sum((Decimal(str(i["total_price"] or 0)) for i in _dos("retida")), Decimal(0))
    parcelas = _dos("parcela")

    # "02 parcelas de R$ 7.720,00 com vencimento em 30 e 60 dias" — a redação da 3.2 do
    # contrato-base. Com valores diferentes entre si, cada uma sai nomeada, para o texto
    # nunca afirmar uma parcela que a tabela não tem.
    if parcelas:
        vals = {Decimal(str(i["total_price"] or 0)) for i in parcelas}
        venc = [str(i["notes"] or "").strip() for i in parcelas]
        if len(vals) == 1:
            desc = (
                f"{len(parcelas):02d} ({_fem(len(parcelas))}) parcela"
                f"{'s' if len(parcelas) > 1 else ''} de {brl(next(iter(vals)))}"
                + (f" com vencimento em {_venc([v for v in venc if v])}" if any(venc) else "")
            )
        else:
            desc = "; ".join(
                f"{brl(Decimal(str(i['total_price'] or 0)))}" + (f" em {str(i['notes']).strip()}" if i["notes"] else "")
                for i in parcelas
            )
    else:
        desc = ""

    pct = (entrada / total * 100).quantize(Decimal("1")) if total else Decimal(0)

    return {
        "valor_total_fmt": brl(total),
        "valor_total_extenso": por_extenso(total),
        "entrada_fmt": brl(entrada),
        "entrada_pct": str(pct),
        "parcelas_descricao": desc,
        "parcela_retida_fmt": brl(retida),
        "conecta_plus_fmt": brl(plus),
        "conecta_plus_extenso": por_extenso(plus),
        "objeto_resumo": (row["description"] or "").strip(),
        "proposta_numero": str(par("proposta_numero")),
        "prazo_exec_dias": str(par("prazo_exec_dias")),
        "prazo_exec_dias_extenso": (
            num_extenso(int(par("prazo_exec_dias", 0))) if str(par("prazo_exec_dias", "")).isdigit() else ""
        ),
        "homologacao_dias": str(par("homologacao_dias")),
        "homologacao_dias_extenso": (
            num_extenso(int(par("homologacao_dias", 0))) if str(par("homologacao_dias", "")).isdigit() else ""
        ),
        "garantia_meses": str(par("garantia_meses")),
        "garantia_meses_extenso": (
            num_extenso(int(par("garantia_meses", 0))) if str(par("garantia_meses", "")).isdigit() else ""
        ),
        "cortesia_meses": str(par("cortesia_meses")),
        "cortesia_meses_extenso": (
            num_extenso(int(par("cortesia_meses", 0))) if str(par("cortesia_meses", "")).isdigit() else ""
        ),
        "multa_atraso_dia": str(par("multa_atraso_dia")),
        "multa_teto_pct": str(par("multa_teto_pct")),
        # ⚠️ `foro` e `cidade_assinatura` SAÍRAM daqui em 18/09/2026 — ver `_foro_e_cidade`.
        # Eles são cláusula de TODO instrumento, não do serviço único; estar aqui era o que
        # travava a emissão de contrato recorrente.
    }


def _foro_e_cidade(row, template: dict) -> dict:
    """`cidade_assinatura` e `foro` para QUALQUER tipo de contrato.

    ⭐ 18/09/2026 — o CTR-2026-00025 (portaria remota, recorrente) ficou em `draft` com todos
    os dados comerciais certos e `content: null`, porque a emissão recusava com
    "sem valor: cidade_assinatura, foro". Medindo: os dois eram lidos SÓ em `_ctx_one_time`,
    que roda apenas quando `contract_type == 'one_time'`. Em contrato recorrente eles nunca
    entravam no contexto, o `StrictUndefined` do Jinja os marcava vazios e `variaveis_vazias`
    reprovava. Os dois modelos recorrentes usam `{{foro}}` no fecho — ou seja, NENHUM contrato
    recorrente conseguia ser emitido por este caminho.

    ⚠️ Eleição de foro em branco indo para assinatura é pior que contrato não emitido, então
    o default NUNCA é vazio. A cadeia é a que o dono definiu:

        cidade_assinatura: contrato (`sla_config`) → cidade do CLIENTE → sede do emitente
                           → "Manaus/AM"
        foro:              contrato (`sla_config`) → "Comarca de " + cidade_assinatura

    Toda a operação da Conecta Mais é em Manaus; o último elo da cadeia é fato, não palpite.
    """
    sla = row["sla_config"] if isinstance(row["sla_config"], dict) else {}
    var = template.get("variables") if isinstance(template.get("variables"), dict) else {}

    def do_contrato(nome):
        v = sla.get(nome)
        if v in (None, ""):
            v = var.get(nome)
        return None if v in (None, "") else str(v).strip()

    cidade = do_contrato("cidade_assinatura")
    if not cidade:
        # cidade do cliente: `clients` guarda em address_city/address_state (não há `cidade`)
        c, uf = (
            (row["cliente_cidade"] if "cliente_cidade" in row.keys() else None),
            (row["cliente_uf"] if "cliente_uf" in row.keys() else None),
        )
        if c:
            cidade = f"{str(c).strip()}/{str(uf).strip()}" if uf else str(c).strip()
    if not cidade:
        cidade = "Manaus/AM"

    foro = do_contrato("foro") or f"Comarca de {cidade}"
    return {"cidade_assinatura": cidade, "foro": foro}


async def montar_contexto(db: AsyncSession, contract_id: str, template: dict) -> tuple[dict, Contratada]:
    """Monta o contexto do render a partir do CONTRATO real. Nada é inventado aqui."""
    row = (await db.execute(text(_SQL_CONTRATO), {"k": contract_id})).mappings().first()
    if not row:
        raise RenderError(f"Contrato não encontrado: {contract_id}")
    itens = (await db.execute(text(_SQL_ITENS), {"k": contract_id})).mappings().all()
    rep = (await db.execute(text(_SQL_REPRESENTANTE), {"k": contract_id})).mappings().first()

    contratada = resolver_contratada(row["tipo_servico"], template.get("service_type"), row["empresa_gravada_cnpj"])

    valor = Decimal(str(row["monthly_value"] or 0))
    meses = None
    if row["start_date"] and row["end_date"]:
        ini, fim = row["start_date"], row["end_date"]
        meses = (fim.year - ini.year) * 12 + (fim.month - ini.month)
        # 01/09/2026 → 31/08/2028 são 24 meses, mas a diferença de mês dá 23: o término é o
        # DIA ANTERIOR ao aniversário. Sem este ajuste o contrato saía "23 (vinte e três)
        # meses" — prazo errado no instrumento.
        if fim.day >= ini.day:
            meses += 1

    rep_cpf, rep_rg = _cpf_rg(rep["notes"] if rep else "")
    conta_texto = await _conta_da_empresa(db, row["empresa_id"])
    ctx = {
        "contratante_nome": nome_proprio(row["cliente_nome"]),
        "contratante_cnpj": cnpj_fmt(row["cliente_cnpj"]),
        "contratante_endereco": row["cliente_endereco"] or "",
        "contratante_representante": nome_proprio(rep["name"] if rep else ""),
        "contratante_representante_cpf": rep_cpf,
        "contratante_representante_rg": rep_rg,
        "contratada_razao_social": contratada.razao_social,
        "contratada_cnpj": contratada.cnpj,
        "contratada_endereco": _SEDE.get(contratada.cnpj, ""),
        # ⚠️ "Jordan Jesus", não "Jordan Santos de Jesus". Eu tinha deixado esta troca
        # PENDENTE por ser o nome que assina instrumento — e o Jordan decidiu na issue
        # CP-MCP-008: o padrão documentado é sem "Santos", como no documento aprovado e
        # anexado ao CTR-2026-00022 (v2). O que identifica juridicamente é o CPF logo
        # abaixo, que não muda; o nome segue o padrão da casa.
        "contratada_representante": "Jordan Jesus",
        "contratada_representante_cpf": "730.681.522-91",
        "contratada_representante_rg": "15398811 SSP/AM",
        # cargo de quem assina: o bloco de assinatura identifica a QUALIDADE em que a
        # pessoa assina, não só o nome — é o que distingue representante de preposto.
        "contratada_cargo": "Diretor Executivo",
        "contratante_cargo": (rep["role"] if rep and rep["role"] else "Síndico"),
        "valor_mensal_fmt": brl(valor),
        "valor_mensal_extenso": por_extenso(valor),
        **_composicao(itens),
        # manutenção eletrônica: inventário e SLA. Vazio faz o render RECUSAR, como no
        # resto — contrato de manutenção sem inventário é preço sem lastro.
        "inventario_sistemas": _inventario(list(itens)),
        "visita_numero": _do_sla(row["sla_config"], "visita_numero", "") or "",
        "visita_data": (_do_sla(row["sla_config"], "visita_data", "") or ""),
        "visitas_mes": (
            num_par(int(_do_sla(row["sla_config"], "visitas_mes", 0)))
            if _do_sla(row["sla_config"], "visitas_mes")
            else ""
        ),
        "prazo_resposta_extenso": (
            num_par(int(_do_sla(row["sla_config"], "prazo_resposta_horas", 0)))
            if _do_sla(row["sla_config"], "prazo_resposta_horas")
            else ""
        ),
        "mes_base_reajuste": (
            f"{_MESES[row['start_date'].month - 1]}/{row['start_date'].year}" if row["start_date"] else ""
        ),
        "dados_bancarios": conta_texto,
        "vigencia_meses_extenso": num_par(meses) if meses else "",
        # Cláusula quarta (redação aprovada pelo Jordan em 21/08): a vigência passou a ter
        # início e fim EXPLÍCITOS e renovação AUTOMÁTICA. Antes dizia "contados a partir da
        # data de sua assinatura, podendo ser renovado por acordo entre as partes" — o que
        # contradizia as duas instruções: começar em 01/09 e renovar sem precisar de acordo.
        # a data do fecho estava FIXA em "17 de junho de 2026" no modelo; agora acompanha
        # o início da vigência, que é quando o instrumento passa a valer.
        "data_assinatura_extenso": data_extenso(row["start_date"]),
        "vigencia_inicio_extenso": data_extenso(row["start_date"]),
        "vigencia_fim_extenso": data_extenso(row["end_date"]),
        "renovacao_aviso_dias_extenso": (
            num_par(int(row["renewal_notification_days"])) if row["renewal_notification_days"] else ""
        ),
        # Dia do vencimento: cláusula negociada, não constante. Vinha como "dia 05 (cinco)"
        # FIXO no corpo do modelo (2x) — o Green Hills negociou dia 8, e o modelo existe
        # para servir vários clientes. Vazio faz o render RECUSAR.
        # o modelo escreve "dia {{dia_vencimento}} ({{dia_vencimento_extenso}})", que é a
        # forma do original ("dia 05 (cinco)") — daí o zero à esquerda.
        "dia_vencimento": f"{int(row['payment_day']):02d}" if row["payment_day"] else "",
        "dia_vencimento_extenso": num_extenso(int(row["payment_day"])) if row["payment_day"] else "",
        # ERRO MEU, corrigido em 21/08: eu lia `notice_period_days` aqui. Aquilo é prazo de
        # AVISO PRÉVIO DE RESCISÃO — outra coisa. Com o default de 30 dias, o render trocou
        # em silêncio os 90 dias que o .docx registrava como "condição comercial
        # especificamente negociada entre as partes". A carência do primeiro pagamento é
        # `grace_period_days`, que é o que o nome diz e não tinha consumidor de regra.
        "primeiro_pagamento_dias_extenso": (num_par(int(row["grace_period_days"])) if row["grace_period_days"] else ""),
    }

    # Contrato de valor ÚNICO: as variáveis de recorrência acima continuam no ctx e apenas
    # não são citadas pelo modelo — `variaveis_vazias` só cobra o que o corpo referencia,
    # então dia de vencimento vazio não reprova um contrato que não tem mensalidade.
    # cláusula de foro e praça de assinatura: TODO instrumento tem, recorrente ou único
    ctx.update(_foro_e_cidade(row, template))

    if (row["contract_type"] or "").strip().lower() == "one_time":
        ctx.update(_ctx_one_time(row, list(itens), template))
        # a data do fecho continua vindo de `start_date`, que é NOT NULL nesta tabela
        # (conferido 09/09) — no serviço único ela é a data da assinatura, não o início de
        # uma vigência que não existe. Não há fallback para hoje: seria o render inventando
        # a data de um instrumento que vai a assinatura.

    # Cortesias NEGOCIADAS, que variam por cliente no mesmo modelo. Default LIGADO: o
    # Green Hills tem as três (bodycam, câmeras da guarita, Conecta Plus) e não pode perdê-
    # las porque um contrato novo dispensou uma. Desligar é ato explícito, por contrato.
    ctx["conecta_plus_cortesia"] = bool(_do_sla(row["sla_config"], "conecta_plus_cortesia", True))

    # Testemunhas: decisão do MODELO, versionada junto com o texto do fecho. Ver
    # `_bloco_assinaturas` — modelo que dispensa testemunha não pode desenhar o quadro.
    var_tpl = template.get("variables") if isinstance(template.get("variables"), dict) else {}
    if var_tpl.get("testemunhas"):
        ctx["testemunhas"] = var_tpl["testemunhas"]

    return ctx, contratada


_COND = re.compile(r"\{%\s*if\s+([a-z_0-9]+)\s*%\}(.*?)\{%\s*endif\s*%\}", re.S)


def variaveis_vazias(ctx: dict, corpo: str) -> list[str]:
    """Variáveis USADAS no corpo que chegariam vazias.

    `StrictUndefined` pega a AUSENTE; string vazia ele deixa passar — e um contrato com
    "contratada 	, CNPJ 	" impresso é tão ruim quanto um com `{{ }}` cru. Esta função
    fecha esse buraco, que o Jinja sozinho não fecha.
    """
    # Cláusula OPCIONAL não exige o dado que ela existe para dispensar. Um
    # `{% if x %}...{{ y }}...{% endif %}` com `x` falso nunca imprime `y`, e cobrar `y`
    # faria a cláusula opcional ser obrigatória na prática. Este pré-passe reproduz o que
    # o Jinja vai fazer, ANTES de cobrar.
    # Origem (10/09/2026): o Kopenhagen não tem a carência de 90 dias nem o Conecta Plus
    # de cortesia que o Green Hills negociou — mesmo modelo, condições diferentes.
    corpo = _COND.sub(lambda m: m.group(2) if ctx.get(m.group(1)) else "", corpo)
    usadas = set(re.findall(r"\{\{\s*([a-z_0-9]+)", corpo))
    return sorted(k for k in usadas if not str(ctx.get(k, "")).strip())


def enderecos_incompletos(ctx: dict) -> list[str]:
    """Endereço que EXISTE e não serve para um instrumento. Aviso, nunca recusa.

    `variaveis_vazias` pega o campo ausente; este pega o campo pela metade, que o outro
    deixa passar. Auditoria do Cowork (11/09/2026): o CTR-2026-00022 saiu com
    `contratante_endereco = "Iranduba/AM"` enquanto o documento aprovado dizia "Rodovia
    Manoel Urbano, Km 12 — Área de Expansão Urbana, Iranduba/AM, CEP 69415-000". O campo
    não estava vazio, estava truncado — e endereço truncado num contrato é problema de
    citação e de foro, não de estética.

    AVISO e não recusa de propósito: há contratante legítimo sem CEP (endereço rural, por
    exemplo), e transformar isto em parede bloquearia emissão correta. Quem decide é quem
    lê — mas agora ele lê ANTES de o papel sair, não depois de o cliente receber.
    """
    ruins = []
    for campo in ("contratante_endereco", "contratada_endereco"):
        valor = str(ctx.get(campo) or "").strip()
        if not valor:
            continue  # ausente é problema de `variaveis_vazias`, não deste
        faltas = []
        if not re.search(r"\d", valor):
            faltas.append("sem número")
        if not re.search(r"\d{5}-?\d{3}", valor):
            faltas.append("sem CEP")
        if len(valor) < 25:
            faltas.append("curto demais para um logradouro")
        if faltas:
            ruins.append(f"{campo}: {valor!r} — {', '.join(faltas)}")
    return ruins


def renderizar(corpo: str, ctx: dict) -> str:
    """MESMO algoritmo do motor do DP: Template(..., undefined=StrictUndefined).render()."""
    try:
        return Template(corpo, undefined=StrictUndefined).render(ctx)
    except Exception as e:  # noqa: BLE001
        raise RenderError(f"Render falhou (variável ausente ou corpo inválido): {e}") from e


# ── PDF ──────────────────────────────────────────────────────────────────────────────
# slug de `pdf_branding` por prestadora. Sem isto o papel timbrado sai SEMPRE pela
# Eletrônica (`empresa_branding` faz `slug or "conecta_eletronica"`) — e um contrato de
# mão de obra com o corpo dizendo PATRIMONIAL e o cabeçalho das 10 páginas dizendo
# ELETRÔNICA é pior que o corpo errado: o erro aparece em toda folha assinada.
_SLUG = {PATRIMONIAL[1]: "conecta_patrimonial", ELETRONICA[1]: "conecta_eletronica"}


def _blocos_em_texto(texto: str, itens: list, total_fmt: str, ctx: dict, assinaturas: list | None = None) -> str:
    """Resolve `[[...]]` na versão TEXTO, espelhando o que o PDF vai mostrar.

    Não é cosmético: é o texto que o agente lê para conferir o instrumento sem abrir
    binário. Token à mostra ali significa que a conferência se faz sobre um documento
    diferente do que vai ao cliente.
    """
    if "[[TABELA_COMPOSICAO]]" in texto:
        linhas = ["COMPOSIÇÃO DO VALOR", ""]
        tot_qtd = 0
        for it in itens:
            # ⚠️ R6-2: `or 1`, não `or 0`. Item gravado antes da correção do wizard tem
            # `quantity = 0` no banco, e documento assinado não pode dizer "qtd 0 · R$ 3.500".
            # A guarda é no RENDER também porque o dado velho não se corrige sozinho — e
            # corrigir só a escrita deixaria os contratos já gravados imprimindo zero.
            q = int(it["quantity"] or 0) or 1
            tot_qtd += q
            linhas.append(f"  {it['service_name'] or '—'} · qtd {q} · {brl(it['total_price'] or 0)}")
            # ⚠️ 18/09/2026 — a descrição também aqui. Consertei a tabela do PDF e este
            # caminho seguiu sem ela: são DUAS montagens da mesma composição, e o
            # `texto_extraido` — que é como o agente CONFERE o documento sem abrir binário —
            # vem desta. Corrigir uma e não a outra é entregar um texto que não descreve o
            # papel que o cliente assina.
            desc = (it["description"] or "").strip() if "description" in it.keys() else ""
            if desc:
                linhas.append(f"      {desc}")
        # ⭐ 18/09/2026 — R8-1: a linha de TOTAL não tem quantidade. Somar quantidades de
        # itens HETEROGÊNEOS não significa nada: 1 sistema + 1 locação não são "2 unidades"
        # de coisa alguma. Antes imprimia `qtd 0`; o conserto da R6 fez o total somar
        # (1+1=2), que é errado de outra forma.
        #
        # ⚠️ E o critério de aceite da R6 dizia "nenhum caminho produz qtd 0" — foi cumprido
        # ao pé da letra e o defeito passou por baixo. A régua mirava o VALOR errado em vez
        # da LINHA errada. Quem escreve o aceite decide o que o teste não vai olhar.
        linhas.append(f"  TOTAL · {total_fmt}")
        texto = texto.replace("[[TABELA_COMPOSICAO]]", "\n".join(linhas))

    if "[[BLOCO_ASSINATURAS]]" in texto:
        # ⚠️ 18/09/2026 — esta montagem e a de `_bloco_assinaturas` (os quadros do PDF) são
        # o MESMO bloco escrito duas vezes. Esta alimenta o `texto_extraido` — como o agente
        # confere o documento sem abrir binário — e, nos modelos que trazem
        # [[BLOCO_ASSINATURAS]] no corpo, o PRÓPRIO PDF. Elas divergiam nos DOIS estados:
        #
        #   · ASSINADO  — o quadro escrevia «Assinado eletronicamente por X»; aqui saía
        #     «✔ assinado ... por X». O oráculo procurava a primeira e acusou o
        #     CTR-2026-00019 de esconder a assinatura do Jordan, que estava lá com outra letra.
        #   · PENDENTE  — o quadro escrevia «Aguardando assinatura eletrônica»; aqui não
        #     saía NADA. O CTR-2026-00025, que ninguém assinou, listava as duas partes como
        #     se estivesse firmado. Contrato que não se declara pendente é documento fabricado.
        #
        # E o silencioso: a data nunca saiu. `assinaturas_do_contrato` devolve a chave
        # `quando`; o trecho lia `data`, que não existe em lugar nenhum — o `if` dava falso e
        # o carimbo saía sem quando desde sempre, sem erro.
        #
        # Por isso o estado agora sai POR PARTE, dentro do mesmo laço que imprime a parte, e
        # não numa varredura solta no fim: quem não assinou tem que aparecer não assinando.
        assinadas = {(a.get("papel") or "").lower(): a for a in (assinaturas or [])}
        linhas = ["ASSINATURAS", ""]
        for papel, ent, pessoa, cargo in (
            (
                "CONTRATADA",
                ctx.get("contratada_razao_social") or ctx.get("contratada_nome"),
                ctx.get("contratada_representante"),
                ctx.get("contratada_cargo"),
            ),
            (
                "CONTRATANTE",
                ctx.get("contratante_nome"),
                ctx.get("contratante_representante"),
                ctx.get("contratante_cargo"),
            ),
        ):
            linhas.append(f"  {papel}: {ent or '—'}")
            linhas.append(f"    por {pessoa or '—'}" + (f" · {cargo}" if cargo else ""))
            a_ = assinadas.get(papel.lower())
            if a_ and a_.get("nome"):
                linhas.append(
                    f"    ✔ Assinado eletronicamente por {a_['nome']}"
                    + (f" em {a_['quando']}" if a_.get("quando") else "")
                )
            else:
                linhas.append("    Aguardando assinatura eletrônica")
        if ctx.get("testemunhas"):
            linhas += ["", "  TESTEMUNHA 1: ____________________", "  TESTEMUNHA 2: ____________________"]
        texto = texto.replace("[[BLOCO_ASSINATURAS]]", "\n".join(linhas))
    return texto


def _esc(txt: str) -> str:
    """Escapa para o mini-HTML do reportlab.

    ⚠️ Nome de item e descrição vêm do cadastro, digitados por gente: um `&` ou um `<` crus
    fazem o `Paragraph` estourar na hora de montar o PDF. Contrato que não gera por causa de
    um "&" no nome do equipamento é o tipo de falha que ninguém associa à causa.
    """
    from xml.sax.saxutils import escape  # noqa: PLC0415

    return escape(str(txt or ""))


def _tabela_composicao(itens: list, total_fmt: str, st: dict):
    """A composição do valor vira TABELA de verdade, centralizada e alinhada.

    Vinha como linhas soltas no texto ("FUNÇÃO/DESCRIÇÃO", "QTD", "PREÇO TOTAL", "AGP
    Diurno", "2", ...), uma por parágrafo — no PDF virava uma coluna de palavras soltas.
    Quantidade centralizada, valor à direita: é assim que se confere dinheiro.
    """
    from reportlab.lib import colors  # noqa: PLC0415
    from reportlab.lib.styles import ParagraphStyle  # noqa: PLC0415
    from reportlab.platypus import (  # noqa: PLC0415
        Paragraph,  # noqa: PLC0415
        Table,
        TableStyle,
    )

    # ⭐ 18/09/2026 — §2 da SPEC: a `descricao` do item vai EMBAIXO do nome, em corpo menor.
    # Ela já era gravada em `contract_items.description` (Text, sem limite) e simplesmente
    # não era impressa — então contrato de LOCAÇÃO não dizia o que está em comodato. No
    # CTR-2026-00025 são 1 totem, 2 leitores faciais, 2 antenas de TAG e 640 tags RFID, e o
    # instrumento saía sem nada disso. É o que o cliente assina e o que a Conecta Mais deve
    # entregar de volta no fim.
    #
    # ⚠️ Isto NÃO é cosmético: o nome é limitado a 200 caracteres (varchar) e a descrição não
    # é. Sem imprimir a descrição, a única forma de detalhar era estourar o nome — que era
    # exatamente o que derrubava o servidor com 500.
    est_nome = ParagraphStyle("it_nome", fontName="Helvetica", fontSize=9.5, leading=11.5)
    est_desc = ParagraphStyle(
        "it_desc",
        fontName="Helvetica",
        fontSize=7.8,
        leading=9.2,
        textColor=colors.HexColor("#4A5568"),
        spaceBefore=1.5,
    )

    linhas = [["FUNÇÃO/DESCRIÇÃO", "QTD", "PREÇO TOTAL"]]
    tot_qtd = 0
    for it in itens:
        q = int(it["quantity"] or 0) or 1  # R6-2: nunca imprime zero (ver versão texto)
        tot_qtd += q
        nome = it["service_name"] or "—"
        desc = (it["description"] or "").strip() if "description" in it.keys() else ""
        celula = (
            [Paragraph(f"<b>{_esc(nome)}</b>", est_nome), Paragraph(_esc(desc), est_desc)]
            if desc
            else Paragraph(f"<b>{_esc(nome)}</b>", est_nome)
        )
        linhas.append([celula, str(q), brl(it["total_price"] or 0)])
    # R8-1: sem quantidade na linha de total — ver a versão em texto para o motivo.
    linhas.append(["TOTAL MENSAL", "", total_fmt])

    t = Table(linhas, colWidths=[88 * mm, 22 * mm, 44 * mm], hAlign="CENTER")
    t.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16277D")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EAF0FF")),
                ("ALIGN", (1, 0), (1, -1), "CENTER"),
                ("ALIGN", (2, 0), (2, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C9D4EA")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return t


def _capa(
    st: dict,
    marca: dict,
    contratante: str,
    cnpj_contratante: str,
    numero: str,
    inicio,
    razao_contratada: str = "",
    cnpj_contratada_fmt: str = "",
    subtitulo: str = "",
) -> list:
    """Capa no padrão-ouro — a mesma de `contract_pdf.build_contract_pdf`.

    O render por modelo abria direto no texto: sem logo, sem título, sem o quadro das
    partes. O contrato da Eletrônica já tinha capa, e é o padrão da casa.
    """
    from reportlab.lib.units import mm as _mm  # noqa: PLC0415
    from reportlab.platypus import Image, PageBreak, Table, TableStyle  # noqa: PLC0415

    el: list = [Spacer(1, 24 * _mm)]
    lp = B.logo_path("cover")
    if lp:
        try:
            img = Image(lp, width=54 * _mm, height=38 * _mm, kind="proportional")
            img.hAlign = "CENTER"
            el.append(img)
        except Exception:  # noqa: BLE001
            pass
    el.append(Spacer(1, 8 * _mm))
    el.append(
        Table(
            [[""]],
            colWidths=[60 * _mm],
            hAlign="CENTER",
            style=TableStyle([("LINEBELOW", (0, 0), (-1, -1), 2.5, B.LARANJA)]),
        )
    )
    el.append(Spacer(1, 10 * _mm))
    el.append(Paragraph("CONTRATO", st["capa_titulo"]))
    el.append(Spacer(1, 2 * _mm))
    # o subtítulo vem do MODELO. Estava fixo em "Portaria 24 Horas": a capa do contrato de
    # manutenção da Eletrônica anunciava portaria — o documento mentia sobre si mesmo já na
    # primeira página.
    el.append(Paragraph(subtitulo or "Prestação de Serviços", st["capa_sub"]))
    el.append(Spacer(1, 12 * _mm))
    box = Table(
        [
            [Paragraph(f"<b>CONTRATANTE:</b> {contratante}", st["capa_meta"])],
            [Paragraph(f"CNPJ: {cnpj_contratante}", st["capa_meta"])],
            # razão social pela grafia que o Jordan definiu (Conecta Mais, separado) e não a
            # do pdf_branding, que traz o "CONECTAMAIS" do registro. A capa dizia um nome e o
            # corpo do contrato, outro.
            [Paragraph(f"<b>CONTRATADA:</b> {razao_contratada}", st["capa_meta"])],
            [Paragraph(f"CNPJ: {cnpj_contratada_fmt}", st["capa_meta"])],
        ],
        colWidths=[150 * _mm],
        hAlign="CENTER",
    )
    box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), B.FUNDO_CLARO),
                ("BOX", (0, 0), (-1, -1), 0.8, B.AZUL_MEDIO),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    el.append(box)
    el.append(Spacer(1, 12 * _mm))
    if numero:
        el.append(Paragraph(f"Contrato <b>{numero}</b>", st["capa_meta"]))
    if inicio:
        el.append(Paragraph(B.data_extenso(inicio), st["capa_meta"]))
    el.append(PageBreak())
    return el


def _bloco_assinaturas(st: dict, ctx: dict, assinaturas: list | None = None, envolver: bool = True):
    """Bloco de assinatura no padrão das plataformas de assinatura eletrônica.

    Por padrão, saem as testemunhas: elas existiam para o contrato valer como título
    executivo extrajudicial (CPC 784, III), e o § 4º do mesmo artigo — Lei 14.620/2023 —
    dispensa testemunha em documento eletrônico cuja integridade seja conferida pelo
    provedor de assinatura. É o caso: hash, IP, user-agent e carimbo de tempo por
    assinatura, com o manifesto ao final.

    EXCEÇÃO, por `ctx["testemunhas"]` (decisão do Jordan em 09/09/2026, para o modelo
    `eletronica_servico_unico`): quando o modelo pedir, saem DOIS quadros de testemunha —
    assinando eletronicamente na mesma plataforma, não em linha manuscrita. É opt-in
    justamente para que manutenção e portaria, que se apoiam na dispensa, não ganhem
    quadro nenhum. ⚠️ O texto de fecho e este bloco andam juntos: um modelo que invoque a
    dispensa do § 4º e ao mesmo tempo peça testemunha contradiz a si mesmo.

    Cada parte ganha um quadro próprio, com nome, cargo e documento — e a linha de
    assinatura vira o registro eletrônico quando assinada. Enquanto pendente, mostra
    "Aguardando assinatura", que é honesto: o contrato ainda não está firmado.
    """
    from reportlab.lib import colors  # noqa: PLC0415
    from reportlab.platypus import Table, TableStyle  # noqa: PLC0415

    assinadas = {(a.get("papel") or "").lower(): a for a in (assinaturas or [])}

    def quadro(papel: str, rotulo: str, entidade: str, doc_: str, pessoa: str, cargo: str):
        a = assinadas.get(papel)
        if a:
            miolo = (
                f"<b>Assinado eletronicamente</b> por {a.get('nome') or pessoa}<br/>"
                f"{a.get('quando', '')}<br/>"
                f"<font size=7>Verificação: {a.get('hash', '')[:32]}</font>"
            )
        else:
            miolo = (
                "<font color='#8A94A6'>_________________________________________<br/>"
                "Aguardando assinatura eletrônica</font>"
            )
        return Table(
            [
                [Paragraph(f"<font color='#16277D' size=11><b>{rotulo}</b></font>", st["cellh"])],
                [Paragraph(miolo, st["assina"] if a else st["small"])],
                [Paragraph(f"<b>{pessoa}</b><br/>{cargo}", st["cell"])],
                [Paragraph(f"{entidade}<br/>{doc_}", st["small"])],
            ],
            colWidths=[160 * mm],
            hAlign="CENTER",
            style=TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#C9D4EA")),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDE6FA")),
                    # filete laranja da marca sob o rótulo — é o que faz o quadro "chamar"
                    ("LINEBELOW", (0, 0), (-1, 0), 1.6, colors.HexColor("#F26522")),
                    ("LINEBELOW", (0, 2), (-1, 2), 0.4, colors.HexColor("#E4EAF5")),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ]
            ),
        )

    from reportlab.platypus import KeepTogether  # noqa: PLC0415

    el: list = [Spacer(1, 10)]
    el.append(
        quadro(
            "contratante",
            "CONTRATANTE",
            ctx.get("contratante_nome", ""),
            f"CNPJ {ctx.get('contratante_cnpj', '')}",
            ctx.get("contratante_representante", ""),
            (ctx.get("contratante_cargo") or "Representante legal")
            + (
                f" · CPF {ctx.get('contratante_representante_cpf')}" if ctx.get("contratante_representante_cpf") else ""
            ),
        )
    )
    el.append(Spacer(1, 30))  # respiro entre as duas assinaturas (pedido do Jordan, 22/08)
    el.append(
        quadro(
            "contratada",
            "CONTRATADA",
            ctx.get("contratada_razao_social", ""),
            f"CNPJ {ctx.get('contratada_cnpj', '')}",
            ctx.get("contratada_representante", ""),
            ctx.get("contratada_cargo") or "Representante legal",
        )
    )

    # Testemunhas — só quando o modelo pede. `testemunhas` pode vir como True (dois quadros
    # em branco, a preencher no ato da assinatura) ou como lista de {nome, cpf} já sabidos.
    tst = ctx.get("testemunhas")
    if tst:
        nomes = tst if isinstance(tst, list) else []
        for i in range(2):
            t = nomes[i] if i < len(nomes) and isinstance(nomes[i], dict) else {}
            cpf = (t.get("cpf") or "").strip()
            el.append(Spacer(1, 20))
            el.append(
                quadro(
                    f"testemunha_{i + 1}",
                    f"TESTEMUNHA {i + 1}",
                    "",
                    f"CPF {cpf}" if cpf else "",
                    t.get("nome") or "A identificar no ato da assinatura",
                    "Testemunha",
                )
            )
    # KeepTogether: os dois quadros vão juntos para a página seguinte em vez de a
    # CONTRATADA ficar órfã no fim da folha, partida ao meio. `envolver=False` quando quem
    # agrupa é o chamador, junto com a última cláusula — dois KeepTogether aninhados fazem
    # o ReportLab medir errado e estourar a folha.
    return [KeepTogether(el)] if envolver else el


def _manifesto(st: dict, contrato: str, manifesto: list) -> list:
    """Manifesto de assinaturas — a página que o próprio contrato promete.

    O fecho do instrumento invoca o art. 784, § 4º do CPC: dispensa testemunha porque a
    integridade "é conferida pelo provedor de assinatura, conforme manifesto ao final".
    Sem esta página o contrato afirmava sobre si mesmo algo que não era verdade — e é
    justamente ela que sustenta a dispensa da testemunha.
    """
    from reportlab.lib import colors  # noqa: PLC0415
    from reportlab.platypus import Table, TableStyle  # noqa: PLC0415

    el: list = [
        PageBreak(),
        Paragraph("MANIFESTO DE ASSINATURAS ELETRÔNICAS", st["h_sec"]),
        Spacer(1, 4),
        Paragraph(
            f"Documento: contrato nº {contrato}. Este manifesto integra o "
            "instrumento e registra a trilha de auditoria de cada assinatura, "
            "na forma do art. 10, § 2º, da MP nº 2.200-2/2001.",
            st["corpo"],
        ),
        Spacer(1, 8),
    ]

    if not manifesto:
        el.append(
            Paragraph(
                "<i>A coleta de assinaturas deste instrumento ainda não foi aberta. Quando as "
                "partes assinarem, esta página passará a registrar nome, documento, data, hora, "
                "endereço IP e o código de verificação de cada assinatura.</i>",
                st["corpo"],
            )
        )
        return el

    cab = ["#", "Parte / signatário", "Situação", "Data e hora", "IP"]
    linhas = [[Paragraph(f"<b>{c}</b>", st["cellh"]) for c in cab]]
    for m in manifesto:
        quem = f"<b>{m['papel']}</b><br/>{m['nome']}"
        if m.get("doc"):
            quem += f"<br/><font size=7>CPF {m['doc']}</font>"
        situacao = "Assinado" if m["assinado"] else "<font color='#8A94A6'>Pendente</font>"
        linhas.append(
            [
                Paragraph(str(m["ordem"]), st["cell"]),
                Paragraph(quem, st["cell"]),
                Paragraph(situacao, st["cell"]),
                Paragraph(m["quando"] or "—", st["cell"]),
                Paragraph(m["ip"] or "—", st["small"]),
            ]
        )
    el.append(
        Table(
            linhas,
            colWidths=[8 * mm, 62 * mm, 24 * mm, 44 * mm, 32 * mm],
            hAlign="CENTER",
            style=TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C9D4EA")),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF0FF")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            ),
        )
    )

    assinados = [m for m in manifesto if m["assinado"]]
    if assinados:
        el.append(Spacer(1, 10))
        el.append(Paragraph("<b>Códigos de verificação</b>", st["cell"]))
        for m in assinados:
            el.append(
                Paragraph(f"{m['nome']} — {m['hash']}<br/><font size=6.5>solicitação {m['req']}</font>", st["small"])
            )
            el.append(Spacer(1, 3))
    el.append(Spacer(1, 8))
    el.append(
        Paragraph(
            "A autenticidade e a integridade deste documento podem ser conferidas junto à "
            "Conecta Mais mediante o número do contrato e os códigos acima.",
            st["small"],
        )
    )
    return el


def build_pdf_do_texto(
    texto: str,
    titulo: str,
    cnpj_contratada: str | None = None,
    itens: list | None = None,
    total_fmt: str = "",
    capa: dict | None = None,
    ctx_assin: dict | None = None,
    assinaturas: list | None = None,
    manifesto: list | None = None,
    numero: str = "",
    subtitulo: str = "",
) -> bytes:
    """Texto renderizado → PDF no padrão visual do CRM (reusa `pdf_branding`).

    O corpo do modelo é texto corrido com parágrafos separados por linha em branco; cada
    parágrafo vira um Paragraph, e o título de cláusula ganha destaque. Não reescreve nada
    do texto jurídico — só apresenta.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=38 * mm, bottomMargin=18 * mm, title=titulo
    )
    # nomes REAIS de pdf_branding.styles(): capa_titulo, capa_sub, capa_meta, destaque,
    # h_sec, corpo, cell, cellr, cellh, assina, small. Um fallback genérico cairia em
    # `small` e imprimiria o contrato inteiro em corpo 7.
    st = B.styles()
    corpo_st, tit_st = st["corpo"], st["h_sec"]

    marca_capa = B.empresa_branding(_SLUG.get(cnpj_contratada or "", "conecta_eletronica"))
    el: list = (
        _capa(
            st,
            marca_capa,
            capa.get("contratante", ""),
            capa.get("cnpj", ""),
            capa.get("numero", ""),
            capa.get("inicio"),
            capa.get("razao_contratada", ""),
            cnpj_contratada or "",
            subtitulo,
        )
        if capa
        else []
    )
    # onde começou a ÚLTIMA cláusula: o fecho (foro + assinaturas) tem de sair na mesma
    # folha. Sem isso o FORO ficava na 10 e a assinatura na 11, com a página do foro
    # terminando no vazio — pedido do Jordan em 22/08.
    inicio_ultima_clausula = len(el)
    for bruto in texto.split("\n"):
        linha = bruto.strip()
        if linha == "[[BLOCO_ASSINATURAS]]":
            from reportlab.platypus import KeepTogether  # noqa: PLC0415

            fecho = el[inicio_ultima_clausula:]
            del el[inicio_ultima_clausula:]
            el.append(KeepTogether(fecho + _bloco_assinaturas(st, ctx_assin or {}, assinaturas, envolver=False)))
            continue
        if linha == "[[TABELA_COMPOSICAO]]":
            el.append(Spacer(1, 6))
            el.append(_tabela_composicao(itens or [], total_fmt, st))
            el.append(Spacer(1, 8))
            continue
        if not linha:
            el.append(Spacer(1, 5))
            continue
        eh_clausula = bool(re.match(r"^\s*(CL[ÁA]USULA|PAR[ÁA]GRAFO)\b", linha, re.I))
        if re.match(r"^\s*CL[ÁA]USULA\b", linha, re.I):
            inicio_ultima_clausula = len(el)
        el.append(Paragraph(linha.replace("&", "&amp;").replace("<", "&lt;"), tit_st if eh_clausula else corpo_st))
        if eh_clausula:
            el.append(Spacer(1, 3))

    # `is not None`, NÃO `if manifesto`: com a lista vazia (assinatura ainda não aberta) o
    # contrato continua prometendo "manifesto ao final" no fecho. Sair sem a página nesse
    # estado é exatamente a promessa não cumprida que o oráculo guarda.
    if manifesto is not None:
        el.extend(_manifesto(st, numero, manifesto))

    # mesmo cabeçalho/rodapé/selo do contract_pdf, MAS com a empresa certa
    marca = B.empresa_branding(_SLUG.get(cnpj_contratada or "", "conecta_eletronica"))

    # `titulo` no canto superior direito: o header_footer já aceitava e eu não passava —
    # por isso o timbrado saía sem identificação do documento, ao contrário do padrão-ouro
    # da Eletrônica.
    # pular_primeira=True quando há capa: a capa é a própria identidade da página, e o
    # cabeçalho por cima dela é o que descaracteriza o padrão-ouro.
    def cb(cv, dc):
        # `def` e não lambda: o `ruff format` quebra a lambda em várias linhas e leva junto o
        # `# noqa: E731` para a linha de dentro, onde ele não silencia nada — o commit seguinte
        # trava num lint que ninguém introduziu. Mesma família do que já cegou parser aqui.
        return B.header_footer(
            cv,
            dc,
            empresa=marca,
            titulo="Contrato",
            seal_watermark=True,
            pular_primeira=bool(capa),
        )

    doc.build(el, onFirstPage=cb, onLaterPages=cb)
    return buf.getvalue()


@dataclass
class Resultado:
    pdf: bytes
    texto: str
    contratada: Contratada
    n_clausulas: int
    clausulas_faltando: list[str] = field(default_factory=list)
    # R6-1: os TÍTULOS, não só a contagem. Congelar `13` não diz quais 13 — e é a lista que
    # permite, meses depois, provar que o instrumento assinado tinha aquelas cláusulas.
    clausulas_do_modelo: list[str] = field(default_factory=list)
    # dado que EXISTE e não serve — endereço truncado, por exemplo. Não impede a emissão;
    # chega a quem está emitindo antes do papel sair.
    avisos: list[str] = field(default_factory=list)


async def renderizar_contrato(
    db: AsyncSession, contract_id: str, template_id: str | None = None, minuta: bool = False
) -> Resultado:
    """Costura completa: contrato + modelo → texto → PDF. É o que a rota chama.

    `minuta=True` gera o RASCUNHO para análise jurídica do cliente: o que ainda não foi
    negociado sai como **[A DEFINIR]** em vez de fazer o render recusar.

    Existe porque a recusa estava certa para o instrumento e errada para a minuta. Em
    10/09/2026 o Jordan pediu a minuta do Kopenhagen para o síndico levar ao jurídico dele
    — e o sistema exigiu o CPF de quem assina, o dia de vencimento e o nome do
    representante, que são exatamente as coisas que ainda vão ser definidas NA análise.
    Pedir o fim para começar o começo.

    ⚠️ A recusa continua valendo para `minuta=False`. Contrato que vai a ASSINATURA com
    campo vazio é pior que erro visível — essa parede não se afrouxa, ganha uma porta.
    """
    if template_id:
        tpl = (
            (
                await db.execute(
                    text(
                        "SELECT id::text, name, service_type, content_template, clauses, variables "
                        "FROM contract_templates WHERE id::text = :t AND coalesce(is_active,true)"
                    ),
                    {"t": template_id},
                )
            )
            .mappings()
            .first()
        )
    else:
        # sem modelo explícito: o do próprio contrato; se não houver, o ativo do tipo dele
        tpl = (
            (
                await db.execute(
                    text("""
            SELECT t.id::text, t.name, t.service_type, t.content_template, t.clauses, t.variables
            FROM contracts c JOIN contract_templates t ON t.id = c.template_id
            WHERE (c.id::text = :k OR c.contract_number = :k) AND coalesce(t.is_active,true)
        """),
                    {"k": contract_id},
                )
            )
            .mappings()
            .first()
        )
    if not tpl:
        raise RenderError(
            "Nenhum modelo indicado e o contrato não tem `template_id`. Escolha o modelo — "
            "gerar contrato sem modelo é o molde de 3 páginas que ninguém quer."
        )
    if not (tpl["content_template"] or "").strip():
        raise RenderError(f"O modelo '{tpl['name']}' está sem corpo (`content_template` vazio).")

    ctx, contratada = await montar_contexto(db, contract_id, dict(tpl))
    itens = (await db.execute(text(_SQL_ITENS), {"k": contract_id})).mappings().all()
    cab = (await db.execute(text(_SQL_CONTRATO), {"k": contract_id})).mappings().first()
    # assinaturas JÁ coletadas. Vazio = "Aguardando assinatura eletrônica" no bloco final;
    # nunca inventa carimbo.
    from modules.crm.services.contract_signature import (  # noqa: PLC0415
        assinaturas_do_contrato,
        manifesto_do_contrato,
    )

    numero = cab["contract_number"] or contract_id
    assinaturas = await assinaturas_do_contrato(db, numero)
    # o manifesto lista TAMBÉM quem ainda não assinou — é trilha de auditoria, não vitrine
    manifesto = await manifesto_do_contrato(db, numero)

    # qualidade do endereço: existe e não serve. Avisa antes do papel sair.
    ctx["_avisos_endereco"] = enderecos_incompletos(ctx)

    vazias = variaveis_vazias(ctx, tpl["content_template"])
    if vazias:
        onde = {
            "contratante_representante": "cadastre em crm_contacts um contato do cliente com role 'Representante legal' "
            "(ou 'Síndico') — é quem assina pelo condomínio",
            "vigencia_inicio_extenso": "defina contracts.start_date",
            "vigencia_fim_extenso": "defina contracts.end_date",
            "renovacao_aviso_dias_extenso": "defina contracts.renewal_notification_days",
            "dia_vencimento": "defina contracts.payment_day (o dia do mês em que vence)",
            "dia_vencimento_extenso": "idem — contracts.payment_day",
            "primeiro_pagamento_dias_extenso": "defina contracts.grace_period_days (carência do 1º pagamento; o .docx do "
            "Green Hills negociou 90 dias)",
            "inventario_sistemas": "lance os sistemas cobertos em contract_items (um por sistema: cancelas, "
            "CFTV, cerca elétrica...) — é o inventário que sustenta o preço",
            "dados_bancarios": "cadastre a conta que RECEBE em bank_accounts da empresa emitente, com "
            "agência, número e chave PIX (allows_receipts=true)",
            "visita_numero": "grave contracts.sla_config->>'visita_numero' (ex.: RV-2026-00001)",
            "visita_data": "grave contracts.sla_config->>'visita_data'",
            "visitas_mes": "grave contracts.sla_config->>'visitas_mes' (visitas preventivas/mês)",
            "prazo_resposta_extenso": "grave contracts.sla_config->>'prazo_resposta_horas' (SLA de corretiva)",
            "contratante_representante_rg": "grave o RG em crm_contacts.notes no formato "
            "'CPF 000.000.000-00 · RG 1234567 SSP/AM'",
            "qtd_diurno": "lance os itens do contrato em contract_items (AGP Diurno / AGP Noturno)",
            "qtd_noturno": "idem — contract_items",
            "qtd_agentes_extenso": "idem — contract_items",
            "valor_diurno_fmt": "idem — contract_items",
            "valor_noturno_fmt": "idem — contract_items",
        }
        if minuta:
            # Na minuta o buraco fica VISÍVEL no papel, com o nome do que falta ao lado —
            # é isso que o jurídico do cliente precisa ver para responder.
            for v in vazias:
                ctx[v] = "[A DEFINIR]"
            vazias = []
    if vazias:
        dicas = sorted({onde[v] for v in vazias if v in onde})
        raise RenderError(
            "Contrato não gerado — sem valor: "
            + ", ".join(vazias)
            + ". "
            + (" · ".join(dicas) if dicas else "")
            + " Campo vazio vai para assinatura assim."
        )

    texto = renderizar(tpl["content_template"], ctx)
    # ⭐ O `texto_extraido` tem de ser 1:1 com o PAPEL. Auditoria do Cowork (11/09/2026):
    # `[[TABELA_COMPOSICAO]]` e `[[BLOCO_ASSINATURAS]]` sobreviviam literalmente no texto,
    # porque eles só viram elemento lá embaixo, na montagem do PDF. E é NO TEXTO que o
    # agente roda os asserts de cláusula — ele estava auditando um documento que não existe.
    # Pior: a composição do valor e quem assina são justamente o que se confere antes de
    # mandar para o cliente, e os dois eram exatamente o que faltava.
    # no contrato de valor ÚNICO a régua é o TOTAL: `valor_mensal_fmt` é R$ 0,00 ali, e a
    # tabela sairia somando parcelas para um total zerado — que é pior que não ter tabela.
    _total_da_tabela = (
        ctx.get("valor_total_fmt")
        if ctx.get("valor_total_fmt") and str(ctx.get("valor_mensal_fmt", "")).endswith("0,00")
        else ctx["valor_mensal_fmt"]
    )
    texto = _blocos_em_texto(texto, list(itens), _total_da_tabela, ctx, assinaturas)

    # subtítulo da capa = o próprio título do instrumento, que é a 1ª linha do modelo.
    # Sai do modelo e não do código: é o modelo que sabe se é portaria ou manutenção.
    primeira = next((ln.strip() for ln in texto.splitlines() if ln.strip()), "")
    if minuta:
        # O papel tem de gritar que é minuta. Um rascunho que circula no jurídico do cliente
        # sem se identificar volta assinado — e aí o "[A DEFINIR]" vira cláusula.
        primeira = "MINUTA PARA ANÁLISE — " + primeira
    # nome_proprio, não capitalize(): o modelo é CAIXA ALTA e `capitalize()` devolvia
    # "Prestação de serviços de portaria" — rebaixando a capa de um contrato já assinado.
    subtitulo = (
        nome_proprio(re.sub(r"^CONTRATO\s+(PARTICULAR\s+)?(DE\s+)?", "", primeira, flags=re.I).strip())
        or "Prestação de Serviços"
    )

    clausulas = tpl["clauses"] if isinstance(tpl["clauses"], list) else []
    faltando = [c for c in clausulas if isinstance(c, str) and c.strip() and c.strip() not in texto]

    titulo = f"Contrato {contract_id}"
    return Resultado(
        avisos=list(ctx.get("_avisos_endereco") or []),
        pdf=build_pdf_do_texto(
            texto,
            titulo,
            contratada.cnpj,
            list(itens),
            ctx["valor_mensal_fmt"],
            capa={
                "contratante": ctx["contratante_nome"],
                "cnpj": ctx["contratante_cnpj"],
                "numero": cab["contract_number"],
                "inicio": cab["start_date"],
                "razao_contratada": contratada.razao_social,
            },
            ctx_assin=ctx,
            assinaturas=assinaturas,
            manifesto=manifesto,
            numero=numero,
            subtitulo=subtitulo,
        ),
        texto=texto,
        contratada=contratada,
        n_clausulas=len(clausulas),
        clausulas_do_modelo=[str(c) for c in clausulas if isinstance(c, str) and c.strip()],
        clausulas_faltando=faltando,
    )
