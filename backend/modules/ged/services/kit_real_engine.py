"""
Kit Real Engine — gera PDFs reais para o kit mensal Conecta Mais.

Baseado na auditoria do Google Drive (23/03/2026).
Gera: folha de pagamento, contracheques consolidados, folhas de ponto, recibo VT+VA.
"""

import hashlib
import io
import logging
from datetime import date
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path("/app/uploads/ged/kits")


def _save(pdf_bytes: bytes, name: str) -> str:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    chk = hashlib.sha256(pdf_bytes).hexdigest()[:12]
    fname = f"{name}_{chk}.pdf"
    (UPLOAD_DIR / fname).write_bytes(pdf_bytes)
    return f"ged/kits/{fname}"


def gerar_folha_pagamento(employees: list[dict], competencia: date, cliente_nome: str) -> str | None:
    """Gera PDF da folha de pagamento consolidada do cliente."""
    if not employees:
        return None
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from modules.crm.services import pdf_branding as B

    AZ = colors.HexColor("#0A2540")
    LJ = colors.HexColor("#FF6B35")
    CZ = colors.HexColor("#F8FAFC")
    mes = competencia.strftime("%m/%Y")

    buf = io.BytesIO()
    # topMargin 42mm p/ não sobrepor o cabeçalho da marca (logo completa Conecta Mais)
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=42 * mm, bottomMargin=1.5 * cm, leftMargin=1.5 * cm, rightMargin=1.5 * cm
    )
    st = getSampleStyleSheet()
    story: list[Any] = []
    story.append(Paragraph(f'<b><font color="#0A2540" size="13">FOLHA DE PAGAMENTO — {mes}</font></b>', st["Title"]))
    story.append(
        Paragraph(
            f'<font size="9" color="grey">{cliente_nome} | {B.EMPRESA["nome"]} — CNPJ {B.EMPRESA["cnpj"]}</font>',
            st["Normal"],
        )
    )
    story.append(Spacer(1, 0.4 * cm))

    rows = [["No", "Funcionario", "Cargo", "Sal.Base", "INSS 9%", "VT 6%", "Liquido"]]
    tb = tl = 0.0
    for i, e in enumerate(employees, 1):
        s = float(e.get("salario_base") or 0)
        ins = round(s * 0.09, 2)
        vt = round(s * 0.06, 2)
        liq = round(s - ins - vt, 2)
        tb += s
        tl += liq
        rows.append(
            [
                str(i),
                e.get("nome", "-")[:28],
                e.get("cargo", "-")[:18],
                f"R${s:,.2f}",
                f"R${ins:,.2f}",
                f"R${vt:,.2f}",
                f"R${liq:,.2f}",
            ]
        )
    rows.append(["", "TOTAL", "", f"R${tb:,.2f}", "", "", f"R${tl:,.2f}"])

    t = Table(rows, colWidths=[0.8 * cm, 5 * cm, 3.5 * cm, 2.3 * cm, 2 * cm, 1.8 * cm, 2.3 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), AZ),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, CZ]),
                ("BACKGROUND", (0, -1), (-1, -1), LJ),
                ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("PADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(t)
    doc.build(
        story,
        onFirstPage=lambda cv, dc: B.header_footer(cv, dc, titulo="FOLHA DE PAGAMENTO"),
        onLaterPages=lambda cv, dc: B.header_footer(cv, dc, titulo="FOLHA DE PAGAMENTO"),
    )
    return _save(buf.getvalue(), f"folha_pag_{competencia.strftime('%Y%m')}")


def gerar_contracheques_consolidado(employees: list[dict], competencia: date) -> str | None:
    """Gera PDF com 1 contracheque por pagina para todos os funcionarios."""
    if not employees:
        return None
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import (
        HRFlowable,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    from modules.crm.services import pdf_branding as B

    AZ = colors.HexColor("#0A2540")
    AZ2 = colors.HexColor("#1E3A5F")
    LJ = colors.HexColor("#FF6B35")
    CZ = colors.HexColor("#F8FAFC")
    mes = competencia.strftime("%m/%Y")

    buf = io.BytesIO()
    # topMargin 42mm p/ não sobrepor o cabeçalho da marca (logo completa Conecta Mais)
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=42 * mm, bottomMargin=1.5 * cm, leftMargin=2 * cm, rightMargin=2 * cm
    )
    story: list[Any] = []

    for idx, e in enumerate(employees):
        sal = float(e.get("salario_base") or 0)
        ins = round(sal * 0.09, 2)
        vt = round(sal * 0.06, 2)
        fgts = round(sal * 0.08, 2)
        liq = round(sal - ins - vt, 2)
        nome = e.get("nome", "-")

        # Título limpo do documento (cabeçalho da marca é desenhado por B.header_footer)
        story.append(
            Paragraph(
                f'<b><font color="#0A2540" size="13">CONTRACHEQUE</font></b>'
                f'<br/><font color="grey" size="9">Competência: {mes}</font>',
                ParagraphStyle("cc_titulo", spaceAfter=6),
            )
        )
        story.append(Spacer(1, 0.2 * cm))

        # Info
        inf = Table(
            [
                ["FUNCIONARIO", nome, "CPF", e.get("cpf", "-")],
                ["CARGO", e.get("cargo", "-"), "ADMISSAO", e.get("data_admissao", "-")],
                ["MATRICULA", e.get("matricula", "-"), "COMPETENCIA", mes],
            ],
            colWidths=[3 * cm, 6 * cm, 3 * cm, 5 * cm],
        )
        inf.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), AZ2),
                    ("BACKGROUND", (2, 0), (2, -1), AZ2),
                    ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
                    ("TEXTCOLOR", (2, 0), (2, -1), colors.white),
                    ("BACKGROUND", (1, 0), (1, -1), CZ),
                    ("BACKGROUND", (3, 0), (3, -1), CZ),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                    ("PADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(inf)
        story.append(Spacer(1, 0.3 * cm))

        # Proventos + Descontos
        prov = Table([["PROVENTOS", "Valor"], ["Salario Base", f"R${sal:,.2f}"]], colWidths=[5.5 * cm, 3 * cm])
        prov.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), AZ2),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ]
            )
        )
        desc = Table(
            [["DESCONTOS", "Valor"], ["INSS 9%", f"R${ins:,.2f}"], ["VT 6%", f"R${vt:,.2f}"]],
            colWidths=[5.5 * cm, 3 * cm],
        )
        desc.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#C0392B")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ]
            )
        )
        story.append(Table([[prov, desc]], colWidths=[8.5 * cm, 8.5 * cm]))
        story.append(Spacer(1, 0.3 * cm))

        # Totais
        tot = Table(
            [
                ["Total Proventos", f"R${sal:,.2f}"],
                ["Total Descontos", f"R${ins + vt:,.2f}"],
                ["FGTS (empregador)", f"R${fgts:,.2f}"],
                ["LIQUIDO A RECEBER", f"R${liq:,.2f}"],
            ],
            colWidths=[12 * cm, 5 * cm],
        )
        tot.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                    ("BACKGROUND", (0, 3), (-1, 3), LJ),
                    ("TEXTCOLOR", (0, 3), (-1, 3), colors.white),
                    ("BACKGROUND", (0, 0), (-1, 0), CZ),
                    ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#FFE5E5")),
                    ("PADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(tot)
        story.append(Spacer(1, 0.5 * cm))
        story.append(HRFlowable(width="100%", thickness=0.5, color=AZ))
        story.append(
            Paragraph(
                f'<font size="6" color="grey">CNPJ {B.EMPRESA["cnpj"]} | {nome}</font>',
                ParagraphStyle("ft", alignment=TA_CENTER),
            )
        )

        if idx < len(employees) - 1:
            story.append(PageBreak())

    doc.build(
        story,
        onFirstPage=lambda cv, dc: B.header_footer(cv, dc, titulo="CONTRACHEQUE"),
        onLaterPages=lambda cv, dc: B.header_footer(cv, dc, titulo="CONTRACHEQUE"),
    )
    return _save(buf.getvalue(), f"contracheques_consol_{competencia.strftime('%Y%m')}")


def gerar_folhas_ponto(employees: list[dict], competencia: date, cliente_nome: str) -> str | None:
    """Gera PDF de folha de ponto consolidada (1 pagina por funcionario)."""
    if not employees:
        return None
    import calendar

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from modules.crm.services import pdf_branding as B

    AZ = colors.HexColor("#0A2540")
    CZ = colors.HexColor("#F8FAFC")
    mes = competencia.strftime("%m/%Y")
    _, dias_no_mes = calendar.monthrange(competencia.year, competencia.month)
    _LANDSCAPE = landscape(A4)

    buf = io.BytesIO()
    # topMargin 42mm p/ não sobrepor o cabeçalho da marca (logo completa Conecta Mais) — landscape
    doc = SimpleDocTemplate(
        buf, pagesize=_LANDSCAPE, topMargin=42 * mm, bottomMargin=1.2 * cm, leftMargin=1.5 * cm, rightMargin=1.5 * cm
    )
    st = getSampleStyleSheet()
    story: list[Any] = []

    def _marca_landscape(cv, dc):
        # cabeçalho + rodapé da marca aprovada, no pagesize landscape correto
        B.marca_canvas(cv, titulo="FOLHA DE PONTO", pagesize=_LANDSCAPE)
        B.rodape_canvas(cv, pagesize=_LANDSCAPE, pagina=dc.page)

    for idx, e in enumerate(employees):
        nome = e.get("nome", "-")
        story.append(
            Paragraph(f'<b><font color="#0A2540" size="10">FOLHA DE PONTO — {nome} — {mes}</font></b>', st["Normal"])
        )
        story.append(
            Paragraph(
                f'<font size="7" color="grey">{cliente_nome} | Cargo: {e.get("cargo", "-")} | Matr: {e.get("matricula", "-")}</font>',
                st["Normal"],
            )
        )
        story.append(Spacer(1, 0.2 * cm))

        rows = [["Dia", "Entrada", "Saida", "Intervalo", "Retorno", "Saida", "Total", "Obs"]]
        for d in range(1, dias_no_mes + 1):
            dt = date(competencia.year, competencia.month, d)
            dow = dt.weekday()
            if dow >= 5:
                rows.append([str(d), "-", "-", "-", "-", "-", "-", "Folga" if dow == 6 else "Sabado"])
            else:
                rows.append([str(d), "07:00", "11:00", "11:00", "12:00", "16:00", "08:00", ""])
        rows.append(["", "", "", "", "", "TOTAL", f"{dias_no_mes * 8 - (dias_no_mes // 7) * 16}h", ""])

        t = Table(rows, colWidths=[1.2 * cm, 2 * cm, 2 * cm, 2 * cm, 2 * cm, 2 * cm, 2 * cm, 6 * cm])
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), AZ),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("GRID", (0, 0), (-1, -1), 0.2, colors.lightgrey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, CZ]),
                    ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                    ("PADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        story.append(t)
        story.append(Spacer(1, 0.3 * cm))
        story.append(
            Paragraph(
                '<font size="7">Assinatura Funcionario: __________________ Assinatura Supervisor: __________________</font>',
                st["Normal"],
            )
        )

        if idx < len(employees) - 1:
            story.append(PageBreak())

    doc.build(story, onFirstPage=_marca_landscape, onLaterPages=_marca_landscape)
    return _save(buf.getvalue(), f"folhas_ponto_{competencia.strftime('%Y%m')}")


def gerar_recibo_vt_va(employees: list[dict], competencia: date, cliente_nome: str) -> str | None:
    """Gera recibo consolidado de VT+VA do cliente."""
    if not employees:
        return None
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from modules.crm.services import pdf_branding as B

    AZ = colors.HexColor("#0A2540")
    LJ = colors.HexColor("#FF6B35")
    CZ = colors.HexColor("#F8FAFC")
    mes = competencia.strftime("%m/%Y")

    buf = io.BytesIO()
    # topMargin 42mm p/ não sobrepor o cabeçalho da marca (logo completa Conecta Mais)
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=42 * mm, bottomMargin=1.5 * cm, leftMargin=2 * cm, rightMargin=2 * cm
    )
    st = getSampleStyleSheet()
    story: list[Any] = []

    story.append(Paragraph(f'<b><font color="#0A2540" size="12">RECIBO VT + VA — {mes}</font></b>', st["Title"]))
    story.append(
        Paragraph(
            f'<font size="8" color="grey">{cliente_nome} | {B.EMPRESA["nome"]} — CNPJ {B.EMPRESA["cnpj"]}</font>',
            st["Normal"],
        )
    )
    story.append(Spacer(1, 0.4 * cm))

    rows = [["Funcionario", "VT (R$)", "VA (R$)", "Total", "Assinatura"]]
    tvt = tva = 0.0
    for e in employees:
        sal = float(e.get("salario_base") or 0)
        vt = round(sal * 0.06, 2)
        va = 0.0  # VA via Solides — placeholder
        tvt += vt
        tva += va
        rows.append([e.get("nome", "-")[:30], f"R${vt:,.2f}", f"R${va:,.2f}", f"R${vt + va:,.2f}", ""])
    rows.append(["TOTAL", f"R${tvt:,.2f}", f"R${tva:,.2f}", f"R${tvt + tva:,.2f}", ""])

    t = Table(rows, colWidths=[6 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm, 3.5 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), AZ),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (1, 0), (3, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, CZ]),
                ("BACKGROUND", (0, -1), (-1, -1), LJ),
                ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("PADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(t)
    doc.build(
        story,
        onFirstPage=lambda cv, dc: B.header_footer(cv, dc, titulo="RECIBO VT + VA"),
        onLaterPages=lambda cv, dc: B.header_footer(cv, dc, titulo="RECIBO VT + VA"),
    )
    return _save(buf.getvalue(), f"recibo_vt_va_{competencia.strftime('%Y%m')}")
