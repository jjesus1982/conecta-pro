"""
Gerador de PDF de CONTRATO no padrão visual Conecta Mais (usa pdf_branding).
build_contract_pdf(c) — c é o objeto Contract (com cliente resolvido em atributos opcionais).
Estrutura: Capa → Partes/Objeto/Valor → Vigência/Reajuste/Cláusulas → Assinaturas (com selo).
"""

from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from modules.crm.services import pdf_branding as B

_TIPO = {"recurring": "Prestação de Serviços Continuados", "one_time": "Prestação de Serviços"}


def _g(c, *names, default=None):
    for n in names:
        v = getattr(c, n, None)
        if v not in (None, ""):
            return v
    return default


def build_contract_pdf(c) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=26 * mm,
        bottomMargin=20 * mm,
        title=f"Contrato {_g(c, 'contract_number', default='')}",
    )
    st = B.styles()
    el: list = []
    numero = _g(c, "contract_number", default="—")
    nome = _g(c, "name", "title", default="Prestação de Serviços")
    cliente = _g(c, "client_name", "cliente", default="Cliente")
    cnpj = _g(c, "client_document", "client_cnpj", "cnpj", default="")
    mensal = float(_g(c, "monthly_value", default=0) or 0)
    total = float(_g(c, "total_value", default=0) or 0)
    inicio = _g(c, "start_date")
    fim = _g(c, "end_date")
    tipo = _TIPO.get(str(_g(c, "contract_type", default="")), "Prestação de Serviços")

    # ---- CAPA ----
    el.append(Spacer(1, 24 * mm))
    lp = B.logo_path("cover")
    if lp:
        try:
            img = Image(lp, width=54 * mm, height=38 * mm, kind="proportional")
            img.hAlign = "CENTER"
            el.append(img)
        except Exception:  # noqa: BLE001
            pass
    el.append(Spacer(1, 8 * mm))
    el.append(
        Table(
            [[""]],
            colWidths=[60 * mm],
            hAlign="CENTER",
            style=TableStyle([("LINEBELOW", (0, 0), (-1, -1), 2.5, B.LARANJA)]),
        )
    )
    el.append(Spacer(1, 10 * mm))
    el.append(Paragraph("CONTRATO", st["capa_titulo"]))
    el.append(Spacer(1, 2 * mm))
    el.append(Paragraph(tipo, st["capa_sub"]))
    el.append(Spacer(1, 12 * mm))
    box = Table(
        [[Paragraph(f"<b>CONTRATANTE:</b> {cliente}", st["capa_meta"])]]
        + ([[Paragraph(f"CNPJ/CPF: {cnpj}", st["capa_meta"])]] if cnpj else [])
        + [
            [Paragraph(f"<b>CONTRATADA:</b> {B.EMPRESA['nome']}", st["capa_meta"])],
            [Paragraph(f"CNPJ: {B.EMPRESA['cnpj']}", st["capa_meta"])],
        ],
        colWidths=[150 * mm],
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
    el.append(Spacer(1, 12 * mm))
    el.append(Paragraph(f"Contrato <b>{numero}</b>", st["capa_meta"]))
    el.append(Paragraph(B.data_extenso(inicio), st["capa_meta"]))
    el.append(PageBreak())

    # ---- PARTES + OBJETO + VALOR ----
    el += B.secao("Das Partes e do Objeto", st)
    el.append(
        Paragraph(
            f"<b>CONTRATADA:</b> {B.EMPRESA['razao']} ({B.EMPRESA['nome']}), inscrita no CNPJ "
            f"{B.EMPRESA['cnpj']}, com sede em {B.EMPRESA['endereco']}.",
            st["corpo"],
        )
    )
    el.append(
        Paragraph(
            f"<b>CONTRATANTE:</b> {cliente}" + (f", inscrita no CNPJ/CPF {cnpj}" if cnpj else "") + ".", st["corpo"]
        )
    )
    el.append(
        Paragraph(
            f"<b>OBJETO:</b> {nome}. A CONTRATADA prestará à CONTRATANTE os serviços de segurança "
            "patrimonial/tecnologia descritos nesta avença, com pessoal próprio, treinado e supervisionado, "
            "e/ou solução tecnológica conforme escopo acordado.",
            st["corpo"],
        )
    )
    if _g(c, "description"):
        el.append(Paragraph(c.description, st["corpo"]))

    el.append(Spacer(1, 3 * mm))
    el += B.secao("Do Valor e das Retenções", st)
    iss = float(_g(c, "retencao_iss", default=0) or 0)
    inss = float(_g(c, "retencao_inss", default=0) or 0)
    csll = float(_g(c, "retencao_csll", default=0) or 0)
    linhas = [["Valor mensal", B.brl(mensal)]]
    if total:
        linhas.append(["Valor total do contrato", B.brl(total)])
    if iss or inss or csll:
        linhas.append(["Retenções (ISS/INSS/CSLL)", B.brl(iss + inss + csll)])
    fin = Table([[a, b] for a, b in linhas], colWidths=[130 * mm, 48 * mm])
    fin.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), B.FONTE),
                ("FONTNAME", (1, 0), (1, -1), B.FONTE_B),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("TEXTCOLOR", (0, 0), (-1, -1), B.TEXTO),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("BACKGROUND", (0, 0), (-1, 0), B.AZUL_ESCURO),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), B.FONTE_B),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E5E7EB")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    el.append(fin)

    el.append(Spacer(1, 3 * mm))
    el += B.secao("Da Vigência e do Reajuste", st)
    vig = f"Vigência de {B.br_date(inicio)} a {B.br_date(fim)}." if fim else f"Início em {B.br_date(inicio)}."
    if _g(c, "auto_renewal"):
        vig += f" Renovação automática por períodos de {_g(c, 'renewal_period_months', default=12)} meses, salvo manifestação em contrário."
    el.append(Paragraph(vig, st["corpo"]))
    el.append(Paragraph("Os valores serão reajustados anualmente pelo índice acordado, na forma da lei.", st["corpo"]))
    el.append(PageBreak())

    # ---- CLÁUSULAS + ASSINATURAS ----
    el += B.secao("Das Cláusulas Gerais", st)
    clausulas = _g(c, "clauses")
    if isinstance(clausulas, list) and clausulas:
        for i, cl in enumerate(clausulas, 1):
            titulo = cl.get("title") or cl.get("titulo") or f"Cláusula {i}" if isinstance(cl, dict) else f"Cláusula {i}"
            corpo = cl.get("text") or cl.get("texto") or "" if isinstance(cl, dict) else str(cl)
            el.append(Paragraph(f"<b>{titulo}.</b> {corpo}", st["corpo"]))
    elif _g(c, "content"):
        el.append(Paragraph(str(c.content).replace("\n", "<br/>"), st["corpo"]))
    else:
        for cl in (
            "<b>Obrigações da CONTRATADA.</b> Executar os serviços com diligência, pessoal treinado e em conformidade com a legislação trabalhista, previdenciária e de segurança.",
            "<b>Obrigações da CONTRATANTE.</b> Efetuar os pagamentos nas datas pactuadas e fornecer as condições necessárias à execução.",
            "<b>Rescisão.</b> O contrato poderá ser rescindido por qualquer das partes mediante aviso prévio de 30 dias.",
            "<b>Confidencialidade e LGPD.</b> As partes tratarão os dados pessoais conforme a Lei 13.709/2018.",
            "<b>Foro.</b> Fica eleito o foro da Comarca de Manaus/AM para dirimir dúvidas oriundas deste contrato.",
        ):
            el.append(Paragraph(cl, st["corpo"]))

    el.append(Spacer(1, 10 * mm))
    el.append(Paragraph(B.data_extenso(inicio), st["corpo"]))
    el.append(Spacer(1, 12 * mm))
    # selo entre as assinaturas
    sp = B.logo_path("seal")
    assinatura = Table(
        [
            [
                [
                    Paragraph("_______________________________", st["corpo"]),
                    Paragraph("<b>CONTRATADA</b>", st["assina"]),
                    Paragraph(f"{B.EMPRESA['nome']}", st["small"]),
                    Paragraph(f"{B.EMPRESA['ceo']} — {B.EMPRESA['ceo_cargo']}", st["small"]),
                ],
                (Image(sp, width=28 * mm, height=28 * mm, kind="proportional") if sp else Paragraph("", st["small"])),
                [
                    Paragraph("_______________________________", st["corpo"]),
                    Paragraph("<b>CONTRATANTE</b>", st["assina"]),
                    Paragraph(f"{cliente}", st["small"]),
                    Paragraph(f"CNPJ/CPF: {cnpj}" if cnpj else "", st["small"]),
                ],
            ]
        ],
        colWidths=[74 * mm, 30 * mm, 74 * mm],
    )
    assinatura.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "CENTER")]))
    el.append(assinatura)

    doc.build(
        el,
        onFirstPage=lambda cv, dc: B.header_footer(cv, dc, seal_watermark=True),
        onLaterPages=lambda cv, dc: B.header_footer(cv, dc, seal_watermark=True),
    )
    return buf.getvalue()
