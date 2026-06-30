"""
Documentos avulsos no padrão Conecta Mais (usa pdf_branding + selo):
- build_recibo_pdf(d): recibo de pagamento (1 página, com selo na assinatura).
- build_ordem_servico_pdf(d): ordem de serviço (OS) com cliente, escopo, responsável e selo.
Ambos PARAMETRIZADOS (recebem um dict) — flexível p/ o Cowork gerar sob demanda.
"""

from __future__ import annotations

import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from modules.crm.services import pdf_branding as B


def _doc(titulo: str) -> tuple:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=28 * mm, bottomMargin=22 * mm, title=titulo
    )
    return buf, doc


def _topo(el, st, titulo: str, numero: str, periodo: str):
    """Bloco de título grande + nº/data no topo da 1ª página (header/footer vêm do branding nas internas)."""
    el.append(Paragraph(titulo, st["capa_titulo"]))
    el.append(Spacer(1, 1 * mm))
    el.append(
        Table(
            [[""]],
            colWidths=[60 * mm],
            hAlign="CENTER",
            style=TableStyle([("LINEBELOW", (0, 0), (-1, -1), 2.2, B.LARANJA)]),
        )
    )
    el.append(Spacer(1, 3 * mm))
    meta = []
    if numero:
        meta.append(f"<b>Nº {numero}</b>")
    meta.append(periodo)
    el.append(Paragraph("&nbsp;&nbsp;•&nbsp;&nbsp;".join(meta), st["capa_meta"]))
    el.append(Spacer(1, 8 * mm))


def _assinatura_selo(el, st, quem: str, sub: str = ""):
    sp = B.logo_path("seal")
    el.append(Spacer(1, 16 * mm))
    el.append(
        Table(
            [
                [
                    (
                        Image(sp, width=26 * mm, height=26 * mm, kind="proportional")
                        if sp
                        else Paragraph("", st["small"])
                    ),
                    [
                        Paragraph("_______________________________", st["corpo"]),
                        Paragraph(f"<b>{quem}</b>", st["assina"]),
                        Paragraph(sub or B.EMPRESA["nome"], st["small"]),
                        Paragraph(f"CNPJ: {B.EMPRESA['cnpj']}", st["small"]),
                    ],
                ]
            ],
            colWidths=[34 * mm, 120 * mm],
            style=TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]),
        )
    )


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
    el.append(Spacer(1, 4 * mm))
    _topo(el, st, "RECIBO", d.get("numero", ""), B.br_date(dt))
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
    _assinatura_selo(el, st, "CONTRATADA / RECEBEDOR")
    doc.build(
        el,
        onFirstPage=lambda c, dc: B.header_footer(c, dc, seal_watermark=True),
        onLaterPages=lambda c, dc: B.header_footer(c, dc, seal_watermark=True),
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
    el.append(Spacer(1, 4 * mm))
    _topo(el, st, "TERMO ADITIVO", d.get("numero", ""), B.br_date(dt))
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
        t = Table([[a, b] for a, b in linhas], colWidths=[120 * mm, 54 * mm])
        t.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (1, 0), (1, -1), B.FONTE_B),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                    ("TEXTCOLOR", (0, 0), (-1, -1), B.TEXTO),
                    ("BACKGROUND", (0, 0), (-1, -1), B.FUNDO_CLARO),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E5E7EB")),
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
    el.append(Spacer(1, 8 * mm))
    el.append(Paragraph(B.data_extenso(dt), st["corpo"]))
    sp = B.logo_path("seal")
    el.append(Spacer(1, 12 * mm))
    el.append(
        Table(
            [
                [
                    [
                        Paragraph("_______________________________", st["corpo"]),
                        Paragraph("<b>CONTRATADA</b>", st["assina"]),
                        Paragraph(B.EMPRESA["nome"], st["small"]),
                        Paragraph(f"{B.EMPRESA['ceo']} — {B.EMPRESA['ceo_cargo']}", st["small"]),
                    ],
                    (
                        Image(sp, width=26 * mm, height=26 * mm, kind="proportional")
                        if sp
                        else Paragraph("", st["small"])
                    ),
                    [
                        Paragraph("_______________________________", st["corpo"]),
                        Paragraph("<b>CONTRATANTE</b>", st["assina"]),
                        Paragraph(cliente, st["small"]),
                        Paragraph(f"CNPJ/CPF: {docnum}" if docnum else "", st["small"]),
                    ],
                ]
            ],
            colWidths=[74 * mm, 30 * mm, 74 * mm],
            style=TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "CENTER")]),
        )
    )
    doc.build(
        el,
        onFirstPage=lambda c, dc: B.header_footer(c, dc, seal_watermark=True),
        onLaterPages=lambda c, dc: B.header_footer(c, dc, seal_watermark=True),
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
    el.append(Spacer(1, 4 * mm))
    _topo(el, st, "ATESTADO DE CAPACIDADE TÉCNICA", d.get("numero", ""), B.br_date(dt))
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
    el.append(Spacer(1, 10 * mm))
    el.append(
        Paragraph(f"{d.get('cidade') or 'Manaus/AM'}, {dt.day} de {B.MESES[dt.month]} de {dt.year}.", st["corpo"])
    )
    # assinatura do EMITENTE (quem atesta) + selo
    sp = B.logo_path("seal")
    el.append(Spacer(1, 16 * mm))
    el.append(
        Table(
            [
                [
                    (
                        Image(sp, width=24 * mm, height=24 * mm, kind="proportional")
                        if sp
                        else Paragraph("", st["small"])
                    ),
                    [
                        Paragraph("_______________________________", st["corpo"]),
                        Paragraph(f"<b>{emitente}</b>", st["assina"]),
                        Paragraph(f"CNPJ/CPF: {emit_doc}" if emit_doc else "", st["small"]),
                        Paragraph(d.get("emitente_responsavel") or "", st["small"]),
                        Paragraph(d.get("emitente_cargo") or "", st["small"]),
                    ],
                ]
            ],
            colWidths=[32 * mm, 122 * mm],
            style=TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]),
        )
    )
    doc.build(
        el,
        onFirstPage=lambda c, dc: B.header_footer(c, dc, seal_watermark=True),
        onLaterPages=lambda c, dc: B.header_footer(c, dc, seal_watermark=True),
    )
    return buf.getvalue()


# ------------------------------------------------------------------ ORDEM DE SERVIÇO
def build_ordem_servico_pdf(d: dict) -> bytes:
    buf, doc = _doc(f"OS {d.get('numero', '')}")
    st = B.styles()
    el: list = []
    dt = d.get("data") or date.today()
    el.append(Spacer(1, 4 * mm))
    _topo(el, st, "ORDEM DE SERVIÇO", d.get("numero", ""), B.br_date(dt))

    info = [
        ("Cliente", d.get("cliente") or "—"),
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

    # assinaturas executor + cliente, com selo no meio
    sp = B.logo_path("seal")
    el.append(Spacer(1, 14 * mm))
    el.append(
        Table(
            [
                [
                    [
                        Paragraph("_______________________________", st["corpo"]),
                        Paragraph("<b>EXECUTANTE</b>", st["assina"]),
                        Paragraph(B.EMPRESA["nome"], st["small"]),
                    ],
                    (
                        Image(sp, width=24 * mm, height=24 * mm, kind="proportional")
                        if sp
                        else Paragraph("", st["small"])
                    ),
                    [
                        Paragraph("_______________________________", st["corpo"]),
                        Paragraph("<b>CLIENTE (ciente)</b>", st["assina"]),
                        Paragraph(d.get("cliente") or "", st["small"]),
                    ],
                ]
            ],
            colWidths=[70 * mm, 28 * mm, 70 * mm],
            style=TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "CENTER")]),
        )
    )
    doc.build(
        el,
        onFirstPage=lambda c, dc: B.header_footer(c, dc, seal_watermark=True),
        onLaterPages=lambda c, dc: B.header_footer(c, dc, seal_watermark=True),
    )
    return buf.getvalue()


# ------------------------------------------------------------------ RELATÓRIO DE VISITA
def build_visit_report_pdf(d: dict) -> bytes:
    """Relatório de Visita Técnica e Comercial (padrão Conecta Mais, com selo)."""
    buf, doc = _doc("Relatório de Visita")
    st = B.styles()
    el: list = []
    cliente = d.get("cliente_nome") or "—"
    dt = d.get("data_visita") or date.today()
    el.append(Spacer(1, 4 * mm))
    _topo(el, st, "RELATÓRIO DE VISITA TÉCNICA E COMERCIAL", d.get("numero", ""), f"{cliente}  •  {B.br_date(dt)}")

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
    _assinatura_selo(el, st, d.get("responsavel") or "Conecta Mais — Vendas e Projetos")
    doc.build(
        el,
        onFirstPage=lambda c, dc: B.header_footer(c, dc, seal_watermark=True),
        onLaterPages=lambda c, dc: B.header_footer(c, dc, seal_watermark=True),
    )
    return buf.getvalue()
