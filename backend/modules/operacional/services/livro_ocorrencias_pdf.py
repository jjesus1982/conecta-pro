"""Livro de ocorrências do posto — PDF do dia, no timbrado padrão-ouro (DGX F8).

Mesma forma do `relatorio_pagamento_pdf`: `pdf_branding.header_footer` (logo real, CNPJ,
rodapé oficial), resumo, tabela cronológica e nota de rodapé dizendo de onde veio cada linha.
Retrato A4: o livro é lido no posto, muitas vezes impresso.
"""

from __future__ import annotations

import io
from datetime import date, datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from modules.crm.services.pdf_branding import (
    AZUL_ESCURO,
    FONTE,
    FONTE_B,
    FUNDO_CLARO,
    TEXTO,
    header_footer,
    secao,
    styles,
)

TIPO_ROTULO = {
    "ocorrencia": "Ocorrência",
    "passagem": "Passagem de turno",
    "checkin": "Check-in do gerente",
    "instrucao": "Instrução de posto",
}


def _esc(s: Any) -> str:
    return str(s if s is not None else "—").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def montar_livro_pdf(posto: str, dia: date, linhas: list[dict], emitido_por: str = "") -> bytes:
    """`linhas`: [{quando: datetime, tipo, quem, titulo, detalhe, grau, situacao, ref}], em ordem cronológica."""
    st = styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=40 * mm,
        bottomMargin=20 * mm,
        title=f"Livro de ocorrencias {posto} {dia:%d-%m-%Y}",
    )
    story: list = []
    story.append(
        Paragraph(
            f"<b>Posto:</b> {_esc(posto)} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Dia:</b> {dia:%d/%m/%Y} "
            f"&nbsp;&nbsp;|&nbsp;&nbsp; <b>Registros:</b> {len(linhas)}",
            st["small"],
        )
    )
    story.append(
        Paragraph(
            f"Emitido em {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            + (f" por {_esc(emitido_por)}" if emitido_por else ""),
            st["small"],
        )
    )
    story.append(Spacer(1, 5 * mm))

    por_tipo = {}
    for ln in linhas:
        por_tipo[ln["tipo"]] = por_tipo.get(ln["tipo"], 0) + 1
    story += secao("Resumo do dia", st)
    resumo = [[TIPO_ROTULO.get(k, k), str(v)] for k, v in por_tipo.items()] or [["Sem registros no dia", "0"]]
    tr = Table(resumo, colWidths=[120 * mm, 58 * mm])
    tr.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), FONTE),
                ("FONTNAME", (0, 0), (0, -1), FONTE_B),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("TEXTCOLOR", (0, 0), (-1, -1), TEXTO),
                ("BACKGROUND", (0, 0), (-1, -1), FUNDO_CLARO),
                ("GRID", (0, 0), (-1, -1), 0.4, AZUL_ESCURO),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(tr)
    story.append(Spacer(1, 6 * mm))

    story += secao("Registros em ordem cronológica", st)
    cab = [Paragraph(h, st["cellh"]) for h in ("Hora", "Tipo", "Registro", "Quem registrou", "Grau / situação")]
    dados = [cab]
    for ln in linhas:
        q = ln.get("quando")
        grau = " / ".join(x for x in (ln.get("grau"), ln.get("situacao")) if x) or "—"
        registro = f"<b>{_esc(ln.get('titulo'))}</b>"
        if ln.get("detalhe"):
            registro += f"<br/>{_esc(str(ln['detalhe'])[:600])}"
        if ln.get("ref"):
            registro += f"<br/><font size='7' color='#6B7280'>{_esc(ln['ref'])}</font>"
        dados.append(
            [
                Paragraph(q.strftime("%H:%M") if q else "—", st["cell"]),
                Paragraph(TIPO_ROTULO.get(ln.get("tipo"), _esc(ln.get("tipo"))), st["cell"]),
                Paragraph(registro, st["cell"]),
                Paragraph(_esc(ln.get("quem")), st["cell"]),
                Paragraph(_esc(grau), st["cell"]),
            ]
        )
    if len(dados) == 1:
        dados.append(
            [
                Paragraph("—", st["cell"]),
                Paragraph("—", st["cell"]),
                Paragraph("Nenhum registro neste dia.", st["cell"]),
                Paragraph("—", st["cell"]),
                Paragraph("—", st["cell"]),
            ]
        )
    tb = Table(dados, colWidths=[14 * mm, 28 * mm, 82 * mm, 30 * mm, 24 * mm], repeatRows=1)
    tb.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), AZUL_ESCURO),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, FUNDO_CLARO]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(tb)
    story.append(Spacer(1, 5 * mm))
    story.append(
        Paragraph(
            "Fontes: ocorrências (occurrences), passagens de turno, check-ins do gerente (visitas de acompanhamento) e "
            "instruções de posto — o mesmo que a tela Livro de ocorrências mostra. Horários em hora de Manaus.",
            st["small"],
        )
    )

    def _hf(canvas, d):
        header_footer(canvas, d, titulo="Livro de Ocorrências", seal_watermark=True)

    doc.build(story, onFirstPage=_hf, onLaterPages=_hf)
    return buf.getvalue()
