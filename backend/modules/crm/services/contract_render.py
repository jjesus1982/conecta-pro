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
SELECT k.name, k.notes
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

    ctx = {
        "contratante_nome": nome_proprio(row["cliente_nome"]),
        "contratante_cnpj": cnpj_fmt(row["cliente_cnpj"]),
        "contratante_endereco": row["cliente_endereco"] or "",
        "contratante_representante": nome_proprio(rep["name"] if rep else ""),
        "contratante_representante_cpf": ((rep["notes"] or "") if rep else ""),
        "contratada_razao_social": contratada.razao_social,
        "contratada_cnpj": contratada.cnpj,
        "contratada_endereco": _SEDE.get(contratada.cnpj, ""),
        "contratada_representante": "Jordan Santos de Jesus",
        "valor_mensal_fmt": brl(valor),
        "valor_mensal_extenso": por_extenso(valor),
        **_composicao(itens),
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


def build_pdf_do_texto(texto: str, titulo: str, cnpj_contratada: str | None = None,
                       itens: list | None = None, total_fmt: str = "") -> bytes:
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

    el: list = []
    for bruto in texto.split("\n"):
        linha = bruto.strip()
        if linha == "[[TABELA_COMPOSICAO]]":
            el.append(Spacer(1, 6))
            el.append(_tabela_composicao(itens or [], total_fmt, st))
            el.append(Spacer(1, 8))
            continue
        if not linha:
            el.append(Spacer(1, 5))
            continue
        eh_clausula = bool(re.match(r"^\s*(CL[ÁA]USULA|PAR[ÁA]GRAFO)\b", linha, re.I))
        el.append(Paragraph(linha.replace("&", "&amp;").replace("<", "&lt;"),
                            tit_st if eh_clausula else corpo_st))
        if eh_clausula:
            el.append(Spacer(1, 3))

    # mesmo cabeçalho/rodapé/selo do contract_pdf, MAS com a empresa certa
    marca = B.empresa_branding(_SLUG.get(cnpj_contratada or "", "conecta_eletronica"))
    # `titulo` no canto superior direito: o header_footer já aceitava e eu não passava —
    # por isso o timbrado saía sem identificação do documento, ao contrário do padrão-ouro
    # da Eletrônica.
    cb = lambda cv, dc: B.header_footer(cv, dc, empresa=marca, titulo="Contrato",  # noqa: E731
                                        seal_watermark=True, pular_primeira=False)
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

    clausulas = tpl["clauses"] if isinstance(tpl["clauses"], list) else []
    faltando = [c for c in clausulas if isinstance(c, str) and c.strip() and c.strip() not in texto]

    titulo = f"Contrato {contract_id}"
    return Resultado(
        pdf=build_pdf_do_texto(texto, titulo, contratada.cnpj, list(itens), ctx["valor_mensal_fmt"]),
        texto=texto,
        contratada=contratada,
        n_clausulas=len(clausulas),
        clausulas_faltando=faltando,
    )
