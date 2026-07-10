"""Gerador de PDF da FOLHA CONSOLIDADA (padrão-ouro Conecta Mais).

Monta um PDF A4 com o resumo da folha do período (totais) + a tabela de
detalhamento por colaborador (proventos/descontos/INSS/FGTS/líquido), usando a
identidade visual centralizada em ``pdf_branding``.

Fonte dos dados: ``calculo_service.get_resumo_folha`` — os mesmos números
exibidos na tela dp/folha. NÃO recalcula nada: só formata em PDF.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from modules.crm.services.pdf_branding import (
    AZUL_ESCURO,
    AZUL_MEDIO,
    FONTE,
    FONTE_B,
    FUNDO_CLARO,
    MESES,
    brl,
    header_footer,
    secao,
    styles,
)


def _fmt_periodo(mes: int, ano: int) -> str:
    nome = MESES[mes] if 1 <= mes <= 12 else str(mes)
    return f"{nome.capitalize()}/{ano}"


def montar_folha_pdf(resumo: dict[str, Any]) -> bytes:
    """Gera os BYTES do PDF da folha consolidada a partir do dict de ``get_resumo_folha``."""
    st = styles()
    mes = int(resumo.get("mes") or 0)
    ano = int(resumo.get("ano") or 0)
    periodo = _fmt_periodo(mes, ano)

    fonte = str(resumo.get("fonte") or "").lower()
    if "portte" in fonte:
        fonte_label = "REAL · Portte Contábil"
    elif "dominio" in fonte or "domínio" in fonte:
        fonte_label = "REAL · Domínio Sistemas"
    elif fonte == "importada":
        fonte_label = "REAL · Folha importada"
    elif "propria" in fonte or "cct" in fonte or "estimativa" in fonte:
        fonte_label = "ESTIMATIVA · Motor CCT (a conciliar)"
    elif fonte:
        fonte_label = f"Fonte: {resumo.get('fonte')}"
    else:
        fonte_label = "—"

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=40 * mm,
        bottomMargin=20 * mm,
        title=f"Folha de Pagamento {periodo}",
    )

    story: list = []

    # ── Subtítulo / metadados ──
    story.append(
        Paragraph(
            f"<b>Competência:</b> {periodo} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"<b>Colaboradores:</b> {int(resumo.get('total_colaboradores') or 0)} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"<b>Fonte:</b> {fonte_label}",
            st["small"],
        )
    )
    story.append(
        Paragraph(
            f"Emitido em {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            st["small"],
        )
    )
    story.append(Spacer(1, 5 * mm))

    # ── Resumo (cards em tabela) ──
    story += secao("Resumo da Folha", st)
    total_bruto = float(resumo.get("total_proventos") or 0)
    total_desc = float(resumo.get("total_descontos") or 0)
    total_liq = float(resumo.get("total_liquido") or 0)
    total_inss = float(resumo.get("total_inss") or 0)
    total_fgts = float(resumo.get("total_fgts") or 0)
    total_irrf = float(resumo.get("total_irrf") or 0)
    custo_total = float(resumo.get("custo_total_empresa") or (total_bruto + total_fgts))

    resumo_rows = [
        ["Total Bruto (Proventos)", brl(total_bruto), "Total INSS", brl(total_inss)],
        ["Total Descontos", brl(total_desc), "Total FGTS 8%", brl(total_fgts)],
        ["Total Líquido (a pagar)", brl(total_liq), "Total IRRF", brl(total_irrf)],
        ["Custo Total Empresa", brl(custo_total), "", ""],
    ]
    tbl_resumo = Table(resumo_rows, colWidths=[45 * mm, 44 * mm, 45 * mm, 44 * mm])
    tbl_resumo.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), FONTE_B),
                ("FONTNAME", (2, 0), (2, -1), FONTE_B),
                ("FONTNAME", (1, 0), (1, -1), FONTE),
                ("FONTNAME", (3, 0), (3, -1), FONTE),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (-1, -1), AZUL_ESCURO),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("ALIGN", (3, 0), (3, -1), "RIGHT"),
                ("BACKGROUND", (0, 0), (-1, -1), FUNDO_CLARO),
                ("BOX", (0, 0), (-1, -1), 0.5, AZUL_MEDIO),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D9E2EC")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(tbl_resumo)
    story.append(Spacer(1, 6 * mm))

    # ── Detalhamento por colaborador ──
    story += secao("Detalhamento por Colaborador", st)
    funcs = resumo.get("funcionarios") or []

    header = [
        Paragraph("Colaborador", st["cellh"]),
        Paragraph("Cargo", st["cellh"]),
        Paragraph("Base", st["cellh"]),
        Paragraph("INSS", st["cellh"]),
        Paragraph("FGTS 8%", st["cellh"]),
        Paragraph("Descontos", st["cellh"]),
        Paragraph("Líquido", st["cellh"]),
    ]
    data_rows = [header]
    for f in funcs:
        data_rows.append(
            [
                Paragraph(str(f.get("nome") or "—"), st["cell"]),
                Paragraph(str(f.get("cargo") or "—"), st["cell"]),
                Paragraph(brl(f.get("salario_base")), st["cellr"]),
                Paragraph(brl(f.get("inss_value")), st["cellr"]),
                Paragraph(brl(f.get("fgts_value")), st["cellr"]),
                Paragraph(brl(f.get("total_descontos")), st["cellr"]),
                Paragraph(brl(f.get("salario_liquido")), st["cellr"]),
            ]
        )

    # Linha de total
    data_rows.append(
        [
            Paragraph("<b>TOTAIS</b>", st["cell"]),
            Paragraph("", st["cell"]),
            Paragraph("", st["cellr"]),
            Paragraph(f"<b>{brl(total_inss)}</b>", st["cellr"]),
            Paragraph(f"<b>{brl(total_fgts)}</b>", st["cellr"]),
            Paragraph(f"<b>{brl(total_desc)}</b>", st["cellr"]),
            Paragraph(f"<b>{brl(total_liq)}</b>", st["cellr"]),
        ]
    )

    col_widths = [42 * mm, 34 * mm, 20 * mm, 18 * mm, 18 * mm, 20 * mm, 22 * mm]
    tbl = Table(data_rows, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), AZUL_ESCURO),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, FUNDO_CLARO]),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E3ECF5")),
                ("LINEABOVE", (0, -1), (-1, -1), 0.8, AZUL_ESCURO),
                ("BOX", (0, 0), (-1, -1), 0.5, AZUL_MEDIO),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D9E2EC")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(tbl)

    story.append(Spacer(1, 6 * mm))
    story.append(
        KeepTogether(
            Paragraph(
                "Documento gerado automaticamente pelo Conecta PRO. Valores conforme a folha "
                "importada/calculada para a competência acima. Confidencial.",
                st["small"],
            )
        )
    )

    def _hf(canvas, doc_):
        header_footer(canvas, doc_, titulo="FOLHA DE PAGAMENTO")

    doc.build(story, onFirstPage=_hf, onLaterPages=_hf)
    return buf.getvalue()
