"""
Documentos avulsos no PADRÃO-OURO Conecta Mais (usa pdf_branding.B):
- build_recibo_pdf(d): recibo de pagamento (assinatura do cliente + empresa).
- build_aditivo_pdf(d): termo aditivo de contrato.
- build_atestado_pdf(d): atestado de capacidade técnica.
- build_ordem_servico_pdf(d): ordem de serviço (OS).
- build_visit_report_pdf(d): relatório de visita técnica e comercial.
Todos PARAMETRIZADOS (recebem um dict). Header/rodapé/assinaturas vêm do módulo B
(centralizados) — mesma moldura visual de proposta/contrato/holerite.
"""

from __future__ import annotations

import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from modules.crm.services import pdf_branding as B


def _doc(titulo: str) -> tuple:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=40 * mm,
        bottomMargin=16 * mm,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        title=titulo,
    )
    return buf, doc


def _meta(st, numero: str, periodo: str) -> list:
    """Linha discreta de nº/data logo abaixo do header branded (título já é do B)."""
    partes = []
    if numero:
        partes.append(f"<b>Nº {numero}</b>")
    if periodo:
        partes.append(periodo)
    if not partes:
        return []
    return [
        Paragraph("&nbsp;&nbsp;•&nbsp;&nbsp;".join(partes), st["capa_meta"]),
        Spacer(1, 6 * mm),
    ]


# ------------------------------------------------------------------ RECIBO
def build_recibo_pdf(d: dict) -> bytes:
    buf, doc = _doc(f"Recibo {d.get('numero', '')}")
    st = B.styles()
    el: list = []
    dt = d.get("data") or date.today()
    valor = float(d.get("valor", 0) or 0)
    pagador = d.get("pagador") or "—"
    docnum = d.get("documento") or ""
    referente = d.get("referente") or "serviços prestados"
    forma = d.get("forma_pagamento")
    el += _meta(st, d.get("numero", ""), B.br_date(dt))
    # valor em destaque
    el.append(
        Table(
            [[Paragraph(f"<b>{B.brl(valor)}</b>", st["capa_titulo"])]],
            colWidths=[80 * mm],
            hAlign="LEFT",
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), B.FUNDO_CLARO),
                    ("BOX", (0, 0), (-1, -1), 0.8, B.AZUL_MEDIO),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ]
            ),
        )
    )
    el.append(Spacer(1, 8 * mm))
    texto = (
        f"Recebemos de <b>{pagador}</b>"
        + (f" (CNPJ/CPF {docnum})" if docnum else "")
        + f" a importância de <b>{B.brl(valor)}</b>, referente a <b>{referente}</b>"
        + (f", pago via {forma}" if forma else "")
        + "."
    )
    el.append(Paragraph(texto, st["corpo"]))
    el.append(Paragraph("Para clareza e devida comprovação, firmamos o presente recibo.", st["corpo"]))
    el.append(Spacer(1, 6 * mm))
    el.append(Paragraph(B.data_extenso(dt), st["corpo"]))
    # quem RECEBE assina (cliente/pagador, manual) + empresa (digital, CEO)
    el += B.campos_assinatura(
        st,
        funcionario_nome=pagador if pagador != "—" else "Cliente",
        funcionario_label="Assinatura do Cliente",
        funcionario_doc_rotulo="CNPJ/CPF",
        funcionario_cpf=docnum or None,
        responsavel_nome=None,
        digital_funcionario=False,
        digital_empresa=True,
    )
    doc.build(
        el,
        onFirstPage=lambda c, dc: B.header_footer(c, dc, titulo="RECIBO"),
        onLaterPages=lambda c, dc: B.header_footer(c, dc, titulo="RECIBO"),
    )
    return buf.getvalue()


# ------------------------------------------------------------------ ADITIVO DE CONTRATO
_ADITIVO_TIPO = {
    "reajuste": "reajuste de valor",
    "prorrogacao": "prorrogação de vigência",
    "escopo": "alteração de escopo",
    "valor": "alteração de valor",
    "outro": "alteração contratual",
}


def build_aditivo_pdf(d: dict) -> bytes:
    buf, doc = _doc(f"Aditivo {d.get('numero', '')}")
    st = B.styles()
    el: list = []
    dt = d.get("data") or date.today()
    contrato = d.get("contrato_numero") or "—"
    cliente = d.get("cliente") or "—"
    docnum = d.get("documento") or ""
    tipo = _ADITIVO_TIPO.get(str(d.get("tipo") or "outro"), "alteração contratual")
    el += _meta(st, d.get("numero", ""), B.br_date(dt))
    el.append(
        Paragraph(
            f"Termo aditivo ao <b>Contrato {contrato}</b>, celebrado entre <b>{B.EMPRESA['razao']}</b> "
            f"({B.EMPRESA['nome']}), CNPJ {B.EMPRESA['cnpj']} (CONTRATADA), e <b>{cliente}</b>"
            + (f", CNPJ/CPF {docnum}" if docnum else "")
            + " (CONTRATANTE).",
            st["corpo"],
        )
    )

    el += B.secao(f"Do Objeto ({tipo})", st)
    el.append(
        Paragraph(
            d.get("objeto")
            or f"As partes acordam o presente {tipo} ao contrato em referência, "
            "permanecendo inalteradas as demais cláusulas.",
            st["corpo"],
        )
    )
    linhas = []
    if d.get("novo_valor") is not None:
        linhas.append(["Novo valor", B.brl(d.get("novo_valor"))])
    if d.get("nova_vigencia_fim"):
        linhas.append(["Nova vigência (término)", str(d["nova_vigencia_fim"])])
    if linhas:
        t = Table(
            [[Paragraph(a, st["cell"]), Paragraph(b, st["cellr"])] for a, b in linhas],
            colWidths=[120 * mm, 54 * mm],
        )
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), B.FUNDO_CLARO),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E5E7EB")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        el.append(Spacer(1, 2 * mm))
        el.append(t)
    if d.get("justificativa"):
        el += B.secao("Da Justificativa", st)
        el.append(Paragraph(str(d["justificativa"]), st["corpo"]))
    el += B.secao("Da Ratificação", st)
    el.append(
        Paragraph(
            "Ficam ratificadas todas as demais cláusulas e condições do contrato original não "
            "modificadas por este termo. E, por estarem assim justas e acordadas, firmam o presente.",
            st["corpo"],
        )
    )
    el.append(Spacer(1, 6 * mm))
    el.append(Paragraph(B.data_extenso(dt), st["corpo"]))
    # CONTRATANTE (cliente, manual) + CONTRATADA (empresa, digital, CEO)
    el += B.campos_assinatura(
        st,
        funcionario_nome=cliente if cliente != "—" else "Cliente",
        funcionario_label="Assinatura do Cliente",
        funcionario_doc_rotulo="CNPJ/CPF",
        funcionario_cpf=docnum or None,
        responsavel_nome=None,
        digital_funcionario=False,
        digital_empresa=True,
    )
    doc.build(
        el,
        onFirstPage=lambda c, dc: B.header_footer(c, dc, titulo="TERMO ADITIVO"),
        onLaterPages=lambda c, dc: B.header_footer(c, dc, titulo="TERMO ADITIVO"),
    )
    return buf.getvalue()


# ------------------------------------------------------------------ ATESTADO DE CAPACIDADE TÉCNICA
def build_atestado_pdf(d: dict) -> bytes:
    buf, doc = _doc(f"Atestado {d.get('numero', '')}")
    st = B.styles()
    el: list = []
    dt = d.get("data") or date.today()
    emitente = d.get("emitente") or "—"
    emit_doc = d.get("emitente_documento") or ""
    servico = d.get("servico") or "serviços de segurança patrimonial e tecnologia"
    periodo = d.get("periodo") or ""
    el += _meta(st, d.get("numero", ""), B.br_date(dt))
    el.append(
        Paragraph(
            f"Atestamos, para os devidos fins de comprovação de capacidade técnica, que a empresa "
            f"<b>{B.EMPRESA['razao']}</b> ({B.EMPRESA['nome']}), inscrita no CNPJ {B.EMPRESA['cnpj']}, "
            f"prestou/presta a esta organização os serviços de <b>{servico}</b>"
            + (f", no período de {periodo}" if periodo else "")
            + (f", no valor de {B.brl(d.get('valor'))}" if d.get("valor") else "")
            + ".",
            st["corpo"],
        )
    )
    el.append(
        Paragraph(
            "Declaramos que os serviços foram executados com <b>qualidade, pontualidade e em total "
            "conformidade</b> com o contratado, nada havendo que desabone sua conduta técnica ou comercial, "
            "razão pela qual atestamos a sua plena capacidade para a prestação dos referidos serviços.",
            st["corpo"],
        )
    )
    if d.get("observacoes"):
        el.append(Paragraph(str(d["observacoes"]), st["corpo"]))
    el.append(Spacer(1, 6 * mm))
    el.append(
        Paragraph(f"{d.get('cidade') or 'Manaus/AM'}, {dt.day} de {B.MESES[dt.month]} de {dt.year}.", st["corpo"])
    )
    # EMITENTE (cliente que atesta, manual) + CONTRATADA (empresa, digital, CEO)
    el += B.campos_assinatura(
        st,
        funcionario_nome=emitente if emitente != "—" else "Emitente",
        funcionario_label="Assinatura do Emitente",
        funcionario_doc_rotulo="CNPJ/CPF",
        funcionario_cpf=emit_doc or None,
        responsavel_nome=None,
        digital_funcionario=False,
        digital_empresa=True,
    )
    doc.build(
        el,
        onFirstPage=lambda c, dc: B.header_footer(c, dc, titulo="ATESTADO DE CAPACIDADE TÉCNICA"),
        onLaterPages=lambda c, dc: B.header_footer(c, dc, titulo="ATESTADO DE CAPACIDADE TÉCNICA"),
    )
    return buf.getvalue()


# ------------------------------------------------------------------ ORDEM DE SERVIÇO
def build_ordem_servico_pdf(d: dict) -> bytes:
    buf, doc = _doc(f"OS {d.get('numero', '')}")
    st = B.styles()
    el: list = []
    dt = d.get("data") or date.today()
    cliente = d.get("cliente") or "—"
    el += _meta(st, d.get("numero", ""), B.br_date(dt))

    info = [
        ("Cliente", cliente),
        ("CNPJ/CPF", d.get("documento") or "—"),
        ("Endereço", d.get("endereco") or "—"),
        ("Responsável", d.get("responsavel") or B.EMPRESA["nome"]),
    ]
    el.append(
        Table(
            [[Paragraph(f"<b>{k}</b>", st["cell"]), Paragraph(str(v), st["cell"])] for k, v in info],
            colWidths=[34 * mm, 140 * mm],
            style=TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.5, B.AZUL_MEDIO),
                    ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E5E7EB")),
                    ("BACKGROUND", (0, 0), (0, -1), B.FUNDO_CLARO),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ]
            ),
        )
    )
    el.append(Spacer(1, 5 * mm))

    el += B.secao("Serviço", st)
    el.append(Paragraph(f"<b>{d.get('servico') or 'Serviço'}</b>", st["corpo"]))
    if d.get("descricao"):
        el.append(Paragraph(str(d["descricao"]).replace("\n", "<br/>"), st["corpo"]))
    if d.get("valor"):
        el.append(Spacer(1, 2 * mm))
        el.append(Paragraph(f"<b>Valor:</b> {B.brl(d.get('valor'))}", st["corpo"]))
    if d.get("prazo"):
        el.append(Paragraph(f"<b>Prazo/Execução:</b> {d['prazo']}", st["corpo"]))

    el.append(Spacer(1, 4 * mm))
    el += B.secao("Observações", st)
    el.append(
        Paragraph(
            d.get("observacoes")
            or "Serviço executado conforme escopo acordado, com equipe "
            "própria e em conformidade com as normas de segurança.",
            st["corpo"],
        )
    )

    # CLIENTE aprova/ciente (manual) + EXECUTANTE empresa (digital, CEO)
    el += B.campos_assinatura(
        st,
        funcionario_nome=cliente if cliente != "—" else "Cliente",
        funcionario_label="Assinatura do Cliente",
        funcionario_doc_rotulo="CNPJ/CPF",
        funcionario_cpf=(d.get("documento") or None),
        responsavel_nome=None,
        digital_funcionario=False,
        digital_empresa=True,
    )
    doc.build(
        el,
        onFirstPage=lambda c, dc: B.header_footer(c, dc, titulo="ORDEM DE SERVIÇO"),
        onLaterPages=lambda c, dc: B.header_footer(c, dc, titulo="ORDEM DE SERVIÇO"),
    )
    return buf.getvalue()


# ------------------------------------------------------------------ RELATÓRIO DE VISITA
def build_visit_report_pdf(d: dict) -> bytes:
    """Relatório de Visita Técnica e Comercial (padrão-ouro Conecta Mais)."""
    buf, doc = _doc("Relatório de Visita")
    st = B.styles()
    el: list = []
    cliente = d.get("cliente_nome") or "—"
    dt = d.get("data_visita") or date.today()
    el += _meta(st, d.get("numero", ""), f"{cliente}  •  {B.br_date(dt)}")

    def bloco(titulo: str, texto) -> None:
        if not texto:
            return
        el.extend(B.secao(titulo, st))
        for par in str(texto).split("\n"):
            if par.strip():
                el.append(Paragraph(par.strip().replace("&", "&amp;"), st["corpo"]))

    bloco("Panorama da visita", d.get("panorama"))
    bloco("Situação atual encontrada", d.get("situacao_atual"))
    bloco("Diagnóstico técnico", d.get("diagnostico_tecnico"))
    bloco("Oportunidade comercial", d.get("oportunidade_comercial"))
    achados = d.get("achados") or []
    if achados:
        el.extend(B.secao("Registros da visita", st))
        for a in achados:
            tipo = (a.get("tipo") if isinstance(a, dict) else None) or "nota"
            desc = (a.get("descricao") if isinstance(a, dict) else str(a)) or ""
            el.append(Paragraph(f"• <b>{tipo}:</b> {str(desc).replace('&', '&amp;')}", st["corpo"]))
    bloco("Próximos passos", d.get("proximos_passos"))
    # responsável pela visita (empresa, digital, CEO por padrão)
    el += B.campos_assinatura(
        st,
        funcionario_nome=cliente if cliente != "—" else "Cliente",
        funcionario_label="Assinatura do Cliente",
        funcionario_doc_rotulo="CNPJ/CPF",
        digital_funcionario=False,
        responsavel_nome=d.get("responsavel") or None,
        digital_empresa=True,
    )
    doc.build(
        el,
        onFirstPage=lambda c, dc: B.header_footer(c, dc, titulo="RELATÓRIO DE VISITA"),
        onLaterPages=lambda c, dc: B.header_footer(c, dc, titulo="RELATÓRIO DE VISITA"),
    )
    return buf.getvalue()


# ---------------------------------------------------------- ORÇAMENTO / PROPOSTA DE PAGAMENTO ÚNICO
def build_orcamento_pdf(d: dict) -> bytes:
    """Orçamento/proposta de PAGAMENTO ÚNICO — abrange MATERIAL, SERVIÇO ou ambos (misto).
    Sem recorrência mensal. Suporta à vista (c/ desconto) e/ou PARCELADO.

    d = {
      numero?, cliente, documento?(CNPJ/CPF), cidade?, data?,
      titulo?, objeto?,                          # objeto = 1 linha resumindo o fornecimento
      itens: [{descricao, qtd?, unidade?, valor_unit, tipo?: 'material'|'servico'}],
      desconto_avista_pct?,                       # ex.: 5
      parcelas?: int, entrada?: float,            # ex.: parcelas=3 -> "3x de R$ X (sem juros)"
      condicoes?: {pagamento?, validade_dias?, garantia?, prazo?, execucao?},
      observacao?,
    }
    Assinatura: cliente (manual) + empresa/CEO (digital)."""
    itens = d.get("itens") or []
    tipos = {(it.get("tipo") or "material").lower() for it in itens}
    misto = len(tipos) > 1
    if misto:
        natureza, nat_label = "ambos", "FORNECIMENTO DE MATERIAL E SERVIÇO"
    elif "servico" in tipos:
        natureza, nat_label = "servico", "PRESTAÇÃO DE SERVIÇO"
    else:
        natureza, nat_label = "material", "VENDA DE MATERIAL"
    # Header sempre curto (não colide com a logo). A natureza vai como destaque no corpo.
    titulo_doc = d.get("titulo") or "PROPOSTA COMERCIAL"
    buf, doc = _doc(titulo_doc)
    st = B.styles()
    el: list = []
    dt = d.get("data") or date.today()
    el += _meta(st, d.get("numero", ""), B.br_date(dt))

    # Selo de natureza (chip laranja) — Venda de Material / Prestação de Serviço / Material e Serviço
    chip = Table(
        [[Paragraph(f'<font color="#FFFFFF"><b>{nat_label}</b></font>', st["small"])]],
        colWidths=[len(nat_label) * 2.2 * mm + 12 * mm], hAlign="LEFT",
    )
    chip.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), B.LARANJA),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    el.append(chip)
    el.append(Spacer(1, 5 * mm))

    cli = d.get("cliente") or "—"
    docnum = d.get("documento") or ""
    cidade = d.get("cidade") or "Manaus/AM"
    ident = f"CNPJ/CPF: {docnum} · {cidade}" if docnum else cidade
    el.append(Paragraph(f"<b>CLIENTE:</b> {cli}", st["corpo"]))
    el.append(Paragraph(ident, st["small"]))
    if d.get("objeto"):
        el.append(Spacer(1, 3 * mm))
        el.append(Paragraph(f"<b>Objeto:</b> {d['objeto']}", st["corpo"]))
    el.append(Spacer(1, 6 * mm))

    el.append(Paragraph("Escopo e Investimento", st["h_sec"]))
    el.append(Spacer(1, 3 * mm))

    _tlabel = {"material": "Material", "servico": "Serviço"}
    if misto:
        header = ["Nº", "Descrição", "Tipo", "Qtd", "Un", "Valor Unit.", "Total"]
        widths = [9 * mm, 62 * mm, 20 * mm, 12 * mm, 11 * mm, 27 * mm, 27 * mm]
    else:
        header = ["Nº", "Descrição", "Qtd", "Un", "Valor Unit.", "Total"]
        widths = [10 * mm, 76 * mm, 14 * mm, 12 * mm, 30 * mm, 36 * mm]
    rows = [[Paragraph(f"<b>{h}</b>", st["cellh"]) for h in header]]
    total = 0.0
    for i, it in enumerate(itens, 1):
        qtd = float(it.get("qtd", 1) or 1)
        vu = float(it.get("valor_unit", 0) or 0)
        tot = qtd * vu
        total += tot
        row = [Paragraph(str(i), st["cell"]), Paragraph(it.get("descricao", ""), st["cell"])]
        if misto:
            row.append(Paragraph(_tlabel.get((it.get("tipo") or "material").lower(), "Material"), st["cell"]))
        row += [
            Paragraph(f"{qtd:g}", st["cellr"]),
            Paragraph(it.get("unidade", "un"), st["cell"]),
            Paragraph(B.brl(vu), st["cellr"]),
            Paragraph(B.brl(tot), st["cellr"]),
        ]
        rows.append(row)
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), B.AZUL_ESCURO),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, B.AZUL_MEDIO),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, B.FUNDO_CLARO]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    el.append(t)
    el.append(Spacer(1, 5 * mm))

    # Bloco de INVESTIMENTO com formas de pagamento (à vista e/ou parcelado)
    desc_pct = float(d.get("desconto_avista_pct", 0) or 0)
    avista = round(total * (1 - desc_pct / 100), 2) if desc_pct > 0 else None
    parcelas = int(d.get("parcelas", 0) or 0)
    entrada = float(d.get("entrada", 0) or 0)

    linhas_pag = [["Valor total", B.brl(total)]]
    if avista is not None:
        linhas_pag.append([f"À vista (−{desc_pct:g}%)", B.brl(avista)])
    if parcelas and parcelas > 1:
        base_parc = total - entrada
        vparc = round(base_parc / parcelas, 2)
        if entrada > 0:
            linhas_pag.append([f"Parcelado", f"entrada {B.brl(entrada)} + {parcelas}x de {B.brl(vparc)}"])
        else:
            linhas_pag.append([f"Parcelado", f"{parcelas}x de {B.brl(vparc)} (sem juros)"])
    tt = Table(
        [[Paragraph(f"<b>{a}</b>", st["cell"]), Paragraph(f"<b>{b}</b>", st["cellr"])] for a, b in linhas_pag],
        colWidths=[110 * mm, 68 * mm], hAlign="RIGHT",
    )
    tt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), B.FUNDO_CLARO),
        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 1.0, B.LARANJA),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, B.AZUL_MEDIO),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    el.append(tt)
    el.append(Spacer(1, 4 * mm))

    nota_padrao = {
        "material": "Venda de material — pagamento único, sem recorrência mensal.",
        "servico": "Serviço avulso — pagamento único, sem recorrência mensal.",
        "ambos": "Fornecimento de material e serviço — pagamento único, sem recorrência mensal.",
    }[natureza]
    el.append(Paragraph(f"<i>{d.get('observacao') or nota_padrao}</i>", st["small"]))
    el.append(Spacer(1, 6 * mm))

    cond = d.get("condicoes") or {}
    el.append(Paragraph("Condições", st["h_sec"]))
    el.append(Spacer(1, 2 * mm))
    if cond.get("pagamento"):
        pag = cond["pagamento"]
    else:
        opcoes = []
        if avista is not None:
            opcoes.append(f"à vista com {desc_pct:g}% de desconto ({B.brl(avista)})")
        if parcelas and parcelas > 1:
            base_parc = total - entrada
            vparc = round(base_parc / parcelas, 2)
            opcoes.append(
                (f"entrada de {B.brl(entrada)} + " if entrada > 0 else "") + f"{parcelas}x de {B.brl(vparc)}"
            )
        pag = "; ou ".join(opcoes) + "." if opcoes else "conforme negociação."
    linhas = [
        f"<b>Pagamento:</b> {pag}",
        f"<b>Validade da proposta:</b> {cond.get('validade_dias', 15)} dias.",
    ]
    if natureza in ("material", "ambos"):
        linhas.append(f"<b>Garantia:</b> {cond.get('garantia') or 'conforme fabricante.'}")
    if natureza in ("servico", "ambos") and cond.get("execucao"):
        linhas.append(f"<b>Execução:</b> {cond['execucao']}")
    prazo_default = "a combinar, conforme disponibilidade de estoque." if natureza == "material" else "a combinar."
    linhas.append(f"<b>Prazo de {'entrega/execução' if natureza=='ambos' else ('entrega' if natureza=='material' else 'execução')}:</b> {cond.get('prazo') or prazo_default}")
    for linha in linhas:
        el.append(Paragraph("• " + linha, st["corpo"]))
    el.append(Spacer(1, 8 * mm))
    el.append(Paragraph(B.data_extenso(dt), st["corpo"]))

    el += B.campos_assinatura(
        st,
        funcionario_nome=cli if cli != "—" else "Cliente",
        funcionario_label="Assinatura do Cliente",
        funcionario_doc_rotulo="CNPJ/CPF",
        funcionario_cpf=docnum or None,
        digital_funcionario=False,
        digital_empresa=True,
    )
    doc.build(
        el,
        onFirstPage=lambda c, dc: B.header_footer(c, dc, titulo=titulo_doc),
        onLaterPages=lambda c, dc: B.header_footer(c, dc, titulo=titulo_doc),
    )
    return buf.getvalue()
