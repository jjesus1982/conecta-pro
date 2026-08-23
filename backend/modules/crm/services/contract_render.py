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

from modules.crm.services import pdf_branding as B

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
    PATRIMONIAL[1]: "Rua Victor Hughes, 19, Conjunto Castelo Branco, Parque 10 de Novembro, "
                    "CEP 69055-630, Manaus/AM",
    ELETRONICA[1]: "Rua Nova Palestina, 51, Crespo, CEP 69073-488, Manaus/AM",
}


# Partículas que ficam em minúscula no meio do nome, e siglas que ficam em caixa alta.
_MINUSC = {"de", "da", "do", "das", "dos", "e", "di", "del", "van", "von", "a"}
_SIGLAS = {"ltda", "me", "epp", "eireli", "s/a", "sa", "s.a", "cnpj", "cpf", "ii", "iii", "iv"}
# Acentos que o cadastro perde por ser digitado em caixa alta sem acentuação.
_ACENTO = {"condominio": "Condomínio", "servicos": "Serviços", "comercio": "Comércio",
           "seguranca": "Segurança", "tecnologia": "Tecnologia", "eletronica": "Eletrônica",
           "predial": "Predial", "sao": "São", "jose": "José", "antonio": "Antônio"}


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
_MAO_DE_OBRA = {"maodeobra", "mao_de_obra", "portaria_mao_de_obra", "portaria_presencial",
                "limpeza", "servicos_gerais"}
_ELETRONICA = {"manutencao_cftv", "portaria_remota", "seguranca_eletronica", "cftv",
               "alarme", "controle_acesso"}


class RenderError(RuntimeError):
    """Falha que NÃO deve virar PDF. Sempre com o motivo em português, para chegar na tela."""


@dataclass
class Contratada:
    razao_social: str
    cnpj: str
    origem: str          # de onde saiu a decisão — vai no relatório, não no contrato
    divergencia: str | None = None   # empresa_id gravada contradiz a regra


def resolver_contratada(tipo_servico: str | None, service_type_modelo: str | None,
                        empresa_gravada_cnpj: str | None = None) -> Contratada:
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
            "Um deles está errado — corrija antes de gerar o contrato.")

    escolhido = do_contrato or do_modelo
    if not escolhido:
        raise RenderError(
            "Não dá para saber quem presta o serviço: o contrato não tem `tipo_servico` e o "
            "modelo não tem `service_type`. Preencha um dos dois — chutar a contratada "
            "colocaria o CNPJ errado num contrato assinado.")

    razao, cnpj = PATRIMONIAL if escolhido == "maodeobra" else ELETRONICA
    origem = "contrato.tipo_servico" if do_contrato else "modelo.service_type"

    diverg = None
    if empresa_gravada_cnpj:
        grav = re.sub(r"\D", "", empresa_gravada_cnpj)
        if grav and grav != re.sub(r"\D", "", cnpj):
            diverg = (f"o contrato aponta empresa_id de CNPJ {empresa_gravada_cnpj}, mas por "
                      f"'{escolhido}' quem presta é {razao} ({cnpj})")
    return Contratada(razao, cnpj, origem, diverg)


# ── Valor por extenso ────────────────────────────────────────────────────────────────
_UNI = ["", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez",
        "onze", "doze", "treze", "quatorze", "quinze", "dezesseis", "dezessete", "dezoito", "dezenove"]
_DEZ = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"]
_CEM = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos", "seiscentos",
        "setecentos", "oitocentos", "novecentos"]


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


_MES_PT = ["", "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
           "agosto", "setembro", "outubro", "novembro", "dezembro"]


def data_extenso(d) -> str:
    """1º de setembro de 2026 — a forma que o contrato usa para datas de vigência."""
    if not d:
        return ""
    dia = "1º" if d.day == 1 else str(d.day)
    return f"{dia} de {_MES_PT[d.month]} de {d.year}"


_NUM_EXT = {1: "um", 2: "dois", 3: "três", 4: "quatro", 5: "cinco", 6: "seis", 7: "sete",
            8: "oito", 9: "nove", 10: "dez", 12: "doze", 15: "quinze", 20: "vinte",
            24: "vinte e quatro", 30: "trinta", 36: "trinta e seis", 48: "quarenta e oito",
            60: "sessenta"}


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
  AND (k.role ILIKE '%representante%' OR k.role ILIKE '%s%ndic%' OR k.role ILIKE '%legal%')
ORDER BY k.is_primary DESC NULLS LAST, k.created_at
LIMIT 1
"""

_SQL_ITENS = """
SELECT i.service_name, i.description, i.quantity, i.unit_price, i.total_price
FROM contract_items i JOIN contracts c ON c.id = i.contract_id
WHERE (c.id::text = :k OR c.contract_number = :k) AND coalesce(i.is_active, true)
ORDER BY i.created_at
"""


_MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
          "setembro", "outubro", "novembro", "dezembro")


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
        rotulo = {"cnpj": "CNPJ", "cpf": "CPF", "email": "e-mail",
                  "telefone": "telefone"}.get((r["pix_key_type"] or "").lower(), "chave")
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
    return {"qtd_diurno": str(dia) if dia else "", "qtd_noturno": str(noite) if noite else "",
            "valor_diurno_fmt": brl(v_dia) if v_dia else "",
            "valor_noturno_fmt": brl(v_noite) if v_noite else "",
            "qtd_agentes_extenso": num_par(dia + noite) if (dia + noite) else ""}


async def montar_contexto(db: AsyncSession, contract_id: str, template: dict) -> tuple[dict, Contratada]:
    """Monta o contexto do render a partir do CONTRATO real. Nada é inventado aqui."""
    row = (await db.execute(text(_SQL_CONTRATO), {"k": contract_id})).mappings().first()
    if not row:
        raise RenderError(f"Contrato não encontrado: {contract_id}")
    itens = (await db.execute(text(_SQL_ITENS), {"k": contract_id})).mappings().all()
    rep = (await db.execute(text(_SQL_REPRESENTANTE), {"k": contract_id})).mappings().first()

    contratada = resolver_contratada(
        row["tipo_servico"], template.get("service_type"), row["empresa_gravada_cnpj"])

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
        "contratada_representante": "Jordan Santos de Jesus",
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
        "visitas_mes": (num_par(int(_do_sla(row["sla_config"], "visitas_mes", 0)))
                        if _do_sla(row["sla_config"], "visitas_mes") else ""),
        "prazo_resposta_extenso": (
            num_par(int(_do_sla(row["sla_config"], "prazo_resposta_horas", 0)))
            if _do_sla(row["sla_config"], "prazo_resposta_horas") else ""),
        "mes_base_reajuste": (f"{_MESES[row['start_date'].month - 1]}/{row['start_date'].year}"
                              if row["start_date"] else ""),
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
        "renovacao_aviso_dias_extenso": (num_par(int(row["renewal_notification_days"]))
                                         if row["renewal_notification_days"] else ""),
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
        "primeiro_pagamento_dias_extenso": (num_par(int(row["grace_period_days"]))
                                            if row["grace_period_days"] else ""),
    }
    return ctx, contratada


def variaveis_vazias(ctx: dict, corpo: str) -> list[str]:
    """Variáveis USADAS no corpo que chegariam vazias.

    `StrictUndefined` pega a AUSENTE; string vazia ele deixa passar — e um contrato com
    "contratada 	, CNPJ 	" impresso é tão ruim quanto um com `{{ }}` cru. Esta função
    fecha esse buraco, que o Jinja sozinho não fecha.
    """
    usadas = set(re.findall(r"\{\{\s*([a-z_0-9]+)", corpo))
    return sorted(k for k in usadas if not str(ctx.get(k, "")).strip())


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


def _tabela_composicao(itens: list, total_fmt: str, st: dict):
    """A composição do valor vira TABELA de verdade, centralizada e alinhada.

    Vinha como linhas soltas no texto ("FUNÇÃO/DESCRIÇÃO", "QTD", "PREÇO TOTAL", "AGP
    Diurno", "2", ...), uma por parágrafo — no PDF virava uma coluna de palavras soltas.
    Quantidade centralizada, valor à direita: é assim que se confere dinheiro.
    """
    from reportlab.lib import colors  # noqa: PLC0415
    from reportlab.platypus import Table, TableStyle  # noqa: PLC0415

    linhas = [["FUNÇÃO/DESCRIÇÃO", "QTD", "PREÇO TOTAL"]]
    tot_qtd = 0
    for it in itens:
        q = int(it["quantity"] or 0)
        tot_qtd += q
        linhas.append([it["service_name"] or "—", str(q), brl(it["total_price"] or 0)])
    linhas.append(["TOTAL MENSAL", str(tot_qtd), total_fmt])

    t = Table(linhas, colWidths=[88 * mm, 22 * mm, 44 * mm], hAlign="CENTER")
    t.setStyle(TableStyle([
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
    ]))
    return t


def _capa(st: dict, marca: dict, contratante: str, cnpj_contratante: str,
          numero: str, inicio, razao_contratada: str = "", cnpj_contratada_fmt: str = "",
          subtitulo: str = "") -> list:
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
    el.append(Table([[""]], colWidths=[60 * _mm], hAlign="CENTER",
                    style=TableStyle([("LINEBELOW", (0, 0), (-1, -1), 2.5, B.LARANJA)])))
    el.append(Spacer(1, 10 * _mm))
    el.append(Paragraph("CONTRATO", st["capa_titulo"]))
    el.append(Spacer(1, 2 * _mm))
    # o subtítulo vem do MODELO. Estava fixo em "Portaria 24 Horas": a capa do contrato de
    # manutenção da Eletrônica anunciava portaria — o documento mentia sobre si mesmo já na
    # primeira página.
    el.append(Paragraph(subtitulo or "Prestação de Serviços", st["capa_sub"]))
    el.append(Spacer(1, 12 * _mm))
    box = Table(
        [[Paragraph(f"<b>CONTRATANTE:</b> {contratante}", st["capa_meta"])],
         [Paragraph(f"CNPJ: {cnpj_contratante}", st["capa_meta"])],
         # razão social pela grafia que o Jordan definiu (Conecta Mais, separado) e não a
         # do pdf_branding, que traz o "CONECTAMAIS" do registro. A capa dizia um nome e o
         # corpo do contrato, outro.
         [Paragraph(f"<b>CONTRATADA:</b> {razao_contratada}", st["capa_meta"])],
         [Paragraph(f"CNPJ: {cnpj_contratada_fmt}", st["capa_meta"])]],
        colWidths=[150 * _mm], hAlign="CENTER")
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), B.FUNDO_CLARO),
        ("BOX", (0, 0), (-1, -1), 0.8, B.AZUL_MEDIO),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    el.append(box)
    el.append(Spacer(1, 12 * _mm))
    if numero:
        el.append(Paragraph(f"Contrato <b>{numero}</b>", st["capa_meta"]))
    if inicio:
        el.append(Paragraph(B.data_extenso(inicio), st["capa_meta"]))
    el.append(PageBreak())
    return el


def _bloco_assinaturas(st: dict, ctx: dict, assinaturas: list | None = None,
                       envolver: bool = True):
    """Bloco de assinatura no padrão das plataformas de assinatura eletrônica.

    Saíram as testemunhas: elas existiam para o contrato valer como título executivo
    extrajudicial (CPC 784, III), e o § 4º do mesmo artigo — Lei 14.620/2023 — dispensa
    testemunha em documento eletrônico cuja integridade seja conferida pelo provedor de
    assinatura. É o caso: hash, IP, user-agent e carimbo de tempo por assinatura, com o
    manifesto ao final.

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
            miolo = (f"<b>Assinado eletronicamente</b> por {a.get('nome') or pessoa}<br/>"
                     f"{a.get('quando', '')}<br/>"
                     f"<font size=7>Verificação: {a.get('hash', '')[:32]}</font>")
        else:
            miolo = ("<font color='#8A94A6'>_________________________________________<br/>"
                     "Aguardando assinatura eletrônica</font>")
        return Table(
            [[Paragraph(f"<font color='#16277D' size=11><b>{rotulo}</b></font>", st["cellh"])],
             [Paragraph(miolo, st["assina"] if a else st["small"])],
             [Paragraph(f"<b>{pessoa}</b><br/>{cargo}", st["cell"])],
             [Paragraph(f"{entidade}<br/>{doc_}", st["small"])]],
            colWidths=[160 * mm], hAlign="CENTER",
            style=TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#C9D4EA")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDE6FA")),
                # filete laranja da marca sob o rótulo — é o que faz o quadro "chamar"
                ("LINEBELOW", (0, 0), (-1, 0), 1.6, colors.HexColor("#F26522")),
                ("LINEBELOW", (0, 2), (-1, 2), 0.4, colors.HexColor("#E4EAF5")),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12)]))

    from reportlab.platypus import KeepTogether  # noqa: PLC0415

    el: list = [Spacer(1, 10)]
    el.append(quadro("contratante", "CONTRATANTE", ctx.get("contratante_nome", ""),
                     f"CNPJ {ctx.get('contratante_cnpj', '')}",
                     ctx.get("contratante_representante", ""),
                     (ctx.get("contratante_cargo") or "Representante legal")
                     + (f" · CPF {ctx.get('contratante_representante_cpf')}"
                        if ctx.get("contratante_representante_cpf") else "")))
    el.append(Spacer(1, 30))  # respiro entre as duas assinaturas (pedido do Jordan, 22/08)
    el.append(quadro("contratada", "CONTRATADA", ctx.get("contratada_razao_social", ""),
                     f"CNPJ {ctx.get('contratada_cnpj', '')}",
                     ctx.get("contratada_representante", ""),
                     ctx.get("contratada_cargo") or "Representante legal"))
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

    el: list = [PageBreak(), Paragraph("MANIFESTO DE ASSINATURAS ELETRÔNICAS", st["h_sec"]),
                Spacer(1, 4),
                Paragraph(f"Documento: contrato nº {contrato}. Este manifesto integra o "
                          "instrumento e registra a trilha de auditoria de cada assinatura, "
                          "na forma do art. 10, § 2º, da MP nº 2.200-2/2001.", st["corpo"]),
                Spacer(1, 8)]

    if not manifesto:
        el.append(Paragraph(
            "<i>A coleta de assinaturas deste instrumento ainda não foi aberta. Quando as "
            "partes assinarem, esta página passará a registrar nome, documento, data, hora, "
            "endereço IP e o código de verificação de cada assinatura.</i>", st["corpo"]))
        return el

    cab = ["#", "Parte / signatário", "Situação", "Data e hora", "IP"]
    linhas = [[Paragraph(f"<b>{c}</b>", st["cellh"]) for c in cab]]
    for m in manifesto:
        quem = f"<b>{m['papel']}</b><br/>{m['nome']}"
        if m.get("doc"):
            quem += f"<br/><font size=7>CPF {m['doc']}</font>"
        situacao = "Assinado" if m["assinado"] else "<font color='#8A94A6'>Pendente</font>"
        linhas.append([Paragraph(str(m["ordem"]), st["cell"]), Paragraph(quem, st["cell"]),
                       Paragraph(situacao, st["cell"]),
                       Paragraph(m["quando"] or "—", st["cell"]),
                       Paragraph(m["ip"] or "—", st["small"])])
    el.append(Table(linhas, colWidths=[8 * mm, 62 * mm, 24 * mm, 44 * mm, 32 * mm],
                    hAlign="CENTER",
                    style=TableStyle([
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C9D4EA")),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF0FF")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5)])))

    assinados = [m for m in manifesto if m["assinado"]]
    if assinados:
        el.append(Spacer(1, 10))
        el.append(Paragraph("<b>Códigos de verificação</b>", st["cell"]))
        for m in assinados:
            el.append(Paragraph(
                f"{m['nome']} — {m['hash']}<br/>"
                f"<font size=6.5>solicitação {m['req']}</font>", st["small"]))
            el.append(Spacer(1, 3))
    el.append(Spacer(1, 8))
    el.append(Paragraph(
        "A autenticidade e a integridade deste documento podem ser conferidas junto à "
        "Conecta Mais mediante o número do contrato e os códigos acima.", st["small"]))
    return el


def build_pdf_do_texto(texto: str, titulo: str, cnpj_contratada: str | None = None,
                       itens: list | None = None, total_fmt: str = "",
                       capa: dict | None = None, ctx_assin: dict | None = None,
                       assinaturas: list | None = None,
                       manifesto: list | None = None, numero: str = "",
                       subtitulo: str = "") -> bytes:
    """Texto renderizado → PDF no padrão visual do CRM (reusa `pdf_branding`).

    O corpo do modelo é texto corrido com parágrafos separados por linha em branco; cada
    parágrafo vira um Paragraph, e o título de cláusula ganha destaque. Não reescreve nada
    do texto jurídico — só apresenta.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=38 * mm, bottomMargin=18 * mm, title=titulo)
    # nomes REAIS de pdf_branding.styles(): capa_titulo, capa_sub, capa_meta, destaque,
    # h_sec, corpo, cell, cellr, cellh, assina, small. Um fallback genérico cairia em
    # `small` e imprimiria o contrato inteiro em corpo 7.
    st = B.styles()
    corpo_st, tit_st = st["corpo"], st["h_sec"]

    marca_capa = B.empresa_branding(_SLUG.get(cnpj_contratada or "", "conecta_eletronica"))
    el: list = _capa(st, marca_capa, capa.get("contratante", ""), capa.get("cnpj", ""),
                     capa.get("numero", ""), capa.get("inicio"),
                     capa.get("razao_contratada", ""), cnpj_contratada or "",
                     subtitulo) if capa else []
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
            el.append(KeepTogether(fecho + _bloco_assinaturas(
                st, ctx_assin or {}, assinaturas, envolver=False)))
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
        el.append(Paragraph(linha.replace("&", "&amp;").replace("<", "&lt;"),
                            tit_st if eh_clausula else corpo_st))
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
    cb = lambda cv, dc: B.header_footer(cv, dc, empresa=marca, titulo="Contrato",  # noqa: E731
                                        seal_watermark=True, pular_primeira=bool(capa))
    doc.build(el, onFirstPage=cb, onLaterPages=cb)
    return buf.getvalue()


@dataclass
class Resultado:
    pdf: bytes
    texto: str
    contratada: Contratada
    n_clausulas: int
    clausulas_faltando: list[str] = field(default_factory=list)


async def renderizar_contrato(db: AsyncSession, contract_id: str,
                              template_id: str | None = None) -> Resultado:
    """Costura completa: contrato + modelo → texto → PDF. É o que a rota chama."""
    if template_id:
        tpl = (await db.execute(text(
            "SELECT id::text, name, service_type, content_template, clauses "
            "FROM contract_templates WHERE id::text = :t AND coalesce(is_active,true)"),
            {"t": template_id})).mappings().first()
    else:
        # sem modelo explícito: o do próprio contrato; se não houver, o ativo do tipo dele
        tpl = (await db.execute(text("""
            SELECT t.id::text, t.name, t.service_type, t.content_template, t.clauses
            FROM contracts c JOIN contract_templates t ON t.id = c.template_id
            WHERE (c.id::text = :k OR c.contract_number = :k) AND coalesce(t.is_active,true)
        """), {"k": contract_id})).mappings().first()
    if not tpl:
        raise RenderError(
            "Nenhum modelo indicado e o contrato não tem `template_id`. Escolha o modelo — "
            "gerar contrato sem modelo é o molde de 3 páginas que ninguém quer.")
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

    vazias = variaveis_vazias(ctx, tpl["content_template"])
    if vazias:
        onde = {
            "contratante_representante":
                "cadastre em crm_contacts um contato do cliente com role 'Representante legal' "
                "(ou 'Síndico') — é quem assina pelo condomínio",
            "vigencia_inicio_extenso": "defina contracts.start_date",
            "vigencia_fim_extenso": "defina contracts.end_date",
            "renovacao_aviso_dias_extenso": "defina contracts.renewal_notification_days",
            "dia_vencimento": "defina contracts.payment_day (o dia do mês em que vence)",
            "dia_vencimento_extenso": "idem — contracts.payment_day",
            "primeiro_pagamento_dias_extenso":
                "defina contracts.grace_period_days (carência do 1º pagamento; o .docx do "
                "Green Hills negociou 90 dias)",
            "inventario_sistemas":
                "lance os sistemas cobertos em contract_items (um por sistema: cancelas, "
                "CFTV, cerca elétrica...) — é o inventário que sustenta o preço",
            "dados_bancarios":
                "cadastre a conta que RECEBE em bank_accounts da empresa emitente, com "
                "agência, número e chave PIX (allows_receipts=true)",
            "visita_numero": "grave contracts.sla_config->>'visita_numero' (ex.: RV-2026-00001)",
            "visita_data": "grave contracts.sla_config->>'visita_data'",
            "visitas_mes": "grave contracts.sla_config->>'visitas_mes' (visitas preventivas/mês)",
            "prazo_resposta_extenso":
                "grave contracts.sla_config->>'prazo_resposta_horas' (SLA de corretiva)",
            "contratante_representante_rg":
                "grave o RG em crm_contacts.notes no formato "
                "'CPF 000.000.000-00 · RG 1234567 SSP/AM'",
            "qtd_diurno": "lance os itens do contrato em contract_items (AGP Diurno / AGP Noturno)",
            "qtd_noturno": "idem — contract_items",
            "qtd_agentes_extenso": "idem — contract_items",
            "valor_diurno_fmt": "idem — contract_items",
            "valor_noturno_fmt": "idem — contract_items",
        }
        dicas = sorted({onde[v] for v in vazias if v in onde})
        raise RenderError(
            "Contrato não gerado — sem valor: " + ", ".join(vazias) + ". "
            + (" · ".join(dicas) if dicas else "")
            + " Campo vazio vai para assinatura assim.")

    texto = renderizar(tpl["content_template"], ctx)

    # subtítulo da capa = o próprio título do instrumento, que é a 1ª linha do modelo.
    # Sai do modelo e não do código: é o modelo que sabe se é portaria ou manutenção.
    primeira = next((ln.strip() for ln in texto.splitlines() if ln.strip()), "")
    # nome_proprio, não capitalize(): o modelo é CAIXA ALTA e `capitalize()` devolvia
    # "Prestação de serviços de portaria" — rebaixando a capa de um contrato já assinado.
    subtitulo = nome_proprio(re.sub(r"^CONTRATO\s+(PARTICULAR\s+)?(DE\s+)?", "", primeira,
                                    flags=re.I).strip()) or "Prestação de Serviços"

    clausulas = tpl["clauses"] if isinstance(tpl["clauses"], list) else []
    faltando = [c for c in clausulas if isinstance(c, str) and c.strip() and c.strip() not in texto]

    titulo = f"Contrato {contract_id}"
    return Resultado(
        pdf=build_pdf_do_texto(
            texto, titulo, contratada.cnpj, list(itens), ctx["valor_mensal_fmt"],
            capa={"contratante": ctx["contratante_nome"], "cnpj": ctx["contratante_cnpj"],
                  "numero": cab["contract_number"], "inicio": cab["start_date"],
                  "razao_contratada": contratada.razao_social},
            ctx_assin=ctx, assinaturas=assinaturas, manifesto=manifesto, numero=numero,
            subtitulo=subtitulo),
        texto=texto,
        contratada=contratada,
        n_clausulas=len(clausulas),
        clausulas_faltando=faltando,
    )
