"""
Gerador de RELATÓRIO no padrão visual Conecta Mais (usa pdf_branding + selo/marca d'água).
build_commercial_report_pdf(ctx) — ctx é um dict com os números comerciais já apurados.
"""

from __future__ import annotations

import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from modules.crm.services import pdf_branding as B

_MESES = B.MESES


def _kpi(label, valor, st):
    return Table(
        [[Paragraph(label, st["small"])], [Paragraph(f"<b>{valor}</b>", st["assina"])]],
        colWidths=[42 * mm],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), B.FUNDO_CLARO),
                ("BOX", (0, 0), (-1, -1), 0.5, B.AZUL_MEDIO),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ]
        ),
    )


def build_commercial_report_pdf(ctx: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=26 * mm,
        bottomMargin=20 * mm,
        title="Relatório Comercial",
    )
    st = B.styles()
    el: list = []
    hoje = ctx.get("data") or date.today()
    periodo = f"{_MESES[hoje.month].capitalize()}/{hoje.year}"

    # CAPA
    el.append(Spacer(1, 26 * mm))
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
    el.append(Paragraph("RELATÓRIO COMERCIAL", st["capa_titulo"]))
    el.append(Spacer(1, 2 * mm))
    el.append(Paragraph(periodo, st["capa_sub"]))
    el.append(Spacer(1, 16 * mm))
    el.append(Paragraph("— CONFIDENCIAL —", st["destaque"]))
    el.append(PageBreak())

    # INDICADORES
    el += B.secao("Indicadores", st)
    kpis = Table(
        [
            [
                _kpi("MRR (recorrente)", B.brl(ctx.get("mrr", 0)), st),
                _kpi("Clientes ativos", str(ctx.get("clientes", 0)), st),
                _kpi("Pipeline aberto", B.brl(ctx.get("pipeline_aberto", 0)), st),
                _kpi("Ganho no mês", B.brl(ctx.get("ganho_mes", 0)), st),
            ]
        ],
        colWidths=[44.5 * mm] * 4,
    )
    kpis.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    el.append(kpis)
    el.append(Spacer(1, 6 * mm))

    # PIPELINE POR ESTÁGIO
    el += B.secao("Pipeline por Estágio", st)
    head = ["Estágio", "Deals", "Valor", "Ponderado"]
    rows = [[Paragraph(h, st["cellh"]) for h in head]]
    for s in ctx.get("por_estagio", []):
        rows.append(
            [
                Paragraph(s.get("estagio", ""), st["cell"]),
                Paragraph(str(s.get("deals", 0)), st["cellr"]),
                Paragraph(B.brl(s.get("valor", 0)), st["cellr"]),
                Paragraph(B.brl(s.get("ponderado", 0)), st["cellr"]),
            ]
        )
    tbl = Table(rows, colWidths=[70 * mm, 28 * mm, 40 * mm, 40 * mm], repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), B.AZUL_ESCURO),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, B.FUNDO_CLARO]),
                ("GRID", (0, 0), (-1, -1), 0.4, B.AZUL_MEDIO),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    el.append(tbl)
    el.append(Spacer(1, 6 * mm))

    # MAIORES DEALS ABERTOS
    if ctx.get("top_deals"):
        el += B.secao("Maiores Negócios Abertos", st)
        head2 = ["Cliente", "Estágio", "Valor"]
        r2 = [[Paragraph(h, st["cellh"]) for h in head2]]
        for d in ctx["top_deals"]:
            r2.append(
                [
                    Paragraph(d.get("cliente", ""), st["cell"]),
                    Paragraph(d.get("estagio", ""), st["cell"]),
                    Paragraph(B.brl(d.get("valor", 0)), st["cellr"]),
                ]
            )
        t2 = Table(r2, colWidths=[98 * mm, 40 * mm, 40 * mm], repeatRows=1)
        t2.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), B.AZUL_ESCURO),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, B.FUNDO_CLARO]),
                    ("GRID", (0, 0), (-1, -1), 0.4, B.AZUL_MEDIO),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        el.append(t2)

    doc.build(
        el,
        onFirstPage=lambda cv, dc: B.header_footer(cv, dc, seal_watermark=True),
        onLaterPages=lambda cv, dc: B.header_footer(cv, dc, seal_watermark=True),
    )
    return buf.getvalue()
